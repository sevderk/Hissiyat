"""Offline CPU encoder shared with the pinned research method."""

import os
import stat
from hashlib import sha1, sha256
from pathlib import Path

MODEL = "sentence-transformers/all-MiniLM-L6-v2"
MODEL_REVISION = "1110a243fdf4706b3f48f1d95db1a4f5529b4d41"
MODEL_SHA256 = "6fd5d72fe4589f189f8ebc006442dbb529bb7ce38f8082112682524616046452"
TOKENIZER_BLOB = "cb202bfe2e3c98645018a6d12f182a434c9d3e02"
MODEL_BYTES = 90_405_214
TOKENIZER_BYTES = 466_247
CPU_THREADS = 2
BATCH_SIZE = 8
MAX_TOKENS = 256
REPOSITORY = Path(__file__).resolve().parents[3]


class ModelUnavailable(RuntimeError):
    pass


def _fixed_local_path(path):
    if str(path).startswith(("\\\\", "//")):
        return False
    if os.name != "nt":
        return True
    from ctypes import windll

    return windll.kernel32.GetDriveTypeW(str(path.anchor)) == 3


def _local_model_directory(directory):
    if directory is None or not directory.is_absolute():
        raise ModelUnavailable("verified_local_model_not_supplied")
    if not _fixed_local_path(directory):
        raise ModelUnavailable("expected_private_local_path")
    directory = directory.resolve(strict=True)
    if not _fixed_local_path(directory) or directory.is_relative_to(REPOSITORY) or not directory.is_dir():
        raise ModelUnavailable("expected_private_local_path")
    return directory


def _bounded_file(path, size):
    info = path.lstat()
    windows_flags = getattr(info, "st_file_attributes", 0)
    if (not stat.S_ISREG(info.st_mode) or info.st_size != size or
            windows_flags & (stat.FILE_ATTRIBUTE_REPARSE_POINT | stat.FILE_ATTRIBUTE_OFFLINE)):
        raise ModelUnavailable("model_integrity_mismatch")
    with path.open("rb") as stream:
        payload = stream.read(size + 1)
    if len(payload) != size:
        raise ModelUnavailable("model_integrity_mismatch")
    return payload


class MiniLMEncoder:
    def __init__(self, directory):
        try:
            directory = _local_model_directory(directory)
            tokenizer_data = _bounded_file(directory / "tokenizer.json", TOKENIZER_BYTES)
            blob = sha1(f"blob {len(tokenizer_data)}\0".encode() + tokenizer_data).hexdigest()
            if blob != TOKENIZER_BLOB:
                raise ModelUnavailable("model_integrity_mismatch")
            weights = _bounded_file(directory / "model.onnx", MODEL_BYTES)
            if sha256(weights).hexdigest() != MODEL_SHA256:
                raise ModelUnavailable("model_integrity_mismatch")

            import onnxruntime as ort
            from tokenizers import Tokenizer

            # Construct from the bytes that passed verification.
            self._tokenizer = Tokenizer.from_str(tokenizer_data.decode("utf-8"))
            self._tokenizer.enable_truncation(max_length=MAX_TOKENS)
            self._tokenizer.enable_padding(pad_id=self._tokenizer.token_to_id("[PAD]"), pad_token="[PAD]")
            options = ort.SessionOptions()
            options.intra_op_num_threads = CPU_THREADS
            options.inter_op_num_threads = 1
            options.log_severity_level = 4
            self._session = ort.InferenceSession(weights, sess_options=options, providers=["CPUExecutionProvider"])
            self._input_names = {item.name for item in self._session.get_inputs()}
            if not {"input_ids", "attention_mask"} <= self._input_names <= {"input_ids", "attention_mask", "token_type_ids"}:
                raise ModelUnavailable("unexpected_model_inputs")
        except ModelUnavailable:
            raise
        except Exception:
            raise ModelUnavailable("local_model_load_failed") from None

    def encode(self, texts, *, reject_truncation=False):
        import numpy as np

        vectors = []
        for offset in range(0, len(texts), BATCH_SIZE):
            batch = self._tokenizer.encode_batch(texts[offset:offset + BATCH_SIZE])
            if reject_truncation and any(item.overflowing for item in batch):
                raise ModelUnavailable("segment_token_budget_exceeded")
            fields = {
                "input_ids": [item.ids for item in batch],
                "attention_mask": [item.attention_mask for item in batch],
                "token_type_ids": [item.type_ids for item in batch],
            }
            encoded = {key: np.asarray(fields[key], dtype=np.int64) for key in self._input_names}
            hidden = self._session.run(None, encoded)[0]
            if hidden.shape != (*encoded["input_ids"].shape, 384) or not np.isfinite(hidden).all():
                raise ModelUnavailable("unexpected_model_output")
            mask = encoded["attention_mask"][..., None]
            pooled = (hidden * mask).sum(axis=1) / mask.sum(axis=1).clip(min=1)
            vectors.append(pooled / np.linalg.norm(pooled, axis=1, keepdims=True).clip(min=1e-12))
        return np.concatenate(vectors).astype(np.float32)
