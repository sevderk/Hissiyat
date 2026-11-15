"""Native one-question review window with no HTTP listener."""

import tkinter as tk
from tkinter import messagebox, ttk

from research.phase_4e import review


def launch(items, state, save, *, window_type=None):
    root = tk.Tk()
    try:
        (window_type or ReviewWindow)(root, items, state, save)
        root.mainloop()
    finally:
        if root.winfo_exists():
            root.destroy()


class ReviewWindow:
    labels_and_definitions = review.LABELS
    context_caption = "B için bağlamsal karar"
    context_guide = "B: Eğitim, iş, kariyer yönü veya gelecekteki fırsatlara ilişkin kişisel belirsizlik arayın."
    context_choices = review.B_DECISIONS
    validate = staticmethod(review.validate_decision)

    def __init__(self, root, items, state, save):
        self.root, self.items, self.state, self.save = root, items, state, save
        root.title("Hissiyat · Yerel CareerNet incelemesi")
        root.geometry("960x790")
        root.minsize(660, 690)
        root.columnconfigure(0, weight=1)
        root.rowconfigure(1, weight=1)
        root.protocol("WM_DELETE_WINDOW", self.close)
        root.report_callback_exception = self._callback_error

        self.heading = ttk.Label(root, padding=(16, 10), font=("Segoe UI", 12, "bold"))
        self.heading.grid(row=0, column=0, sticky="ew")
        reading = ttk.Frame(root, padding=(16, 0))
        reading.grid(row=1, column=0, sticky="nsew")
        reading.columnconfigure(0, weight=1)
        reading.rowconfigure(0, weight=1)
        self.question = tk.Text(reading, wrap="word", height=8, padx=10, pady=8, font=("Segoe UI", 12),
                                exportselection=False, takefocus=False)
        scroll = ttk.Scrollbar(reading, command=self.question.yview)
        self.question.configure(yscrollcommand=scroll.set)
        self.question.grid(row=0, column=0, sticky="nsew")
        scroll.grid(row=0, column=1, sticky="ns")
        for event in ("<<Copy>>", "<<Cut>>", "<Control-c>", "<Control-Insert>"):
            self.question.bind(event, lambda _event: "break")

        form = ttk.Frame(root, padding=(16, 10))
        form.grid(row=2, column=0, sticky="ew")
        form.columnconfigure(1, weight=1)
        self.privacy = self.choice(form, 0, "Mahremiyet", review.PRIVACY.values())
        self.b_choice = self.choice(form, 1, self.context_caption, self.context_choices.values())
        ttk.Separator(form).grid(row=2, columnspan=2, sticky="ew", pady=6)
        self.labels = {}
        for row, (key, (label, _definition)) in enumerate(self.labels_and_definitions.items(), start=3):
            choices = list(review.EVIDENCE.values())
            if key == "emotion":
                choices.remove(review.EVIDENCE["contextual"])
            self.labels[key] = self.choice(form, row, label, choices)
        self.insufficient = tk.BooleanVar()
        self.insufficient_control = ttk.Checkbutton(
            form, text="Yetersiz veya belirsiz kanıt", variable=self.insufficient
        )
        guide_row = 3 + len(self.labels_and_definitions)
        self.insufficient_control.grid(row=guide_row, column=0, sticky="w", pady=(5, 0))
        ttk.Button(form, text="Etiket kılavuzu", command=self.guide).grid(row=guide_row, column=1, sticky="e")

        footer = ttk.Frame(root, padding=(16, 0, 16, 12))
        footer.grid(row=3, column=0, sticky="ew")
        self.previous = ttk.Button(footer, text="Önceki", command=lambda: self.move(-1))
        self.previous.pack(side="left")
        ttk.Button(footer, text="Kaydet", command=self.save_current).pack(side="left", padx=8)
        self.next = ttk.Button(footer, text="Sonraki", command=lambda: self.move(1))
        self.next.pack(side="left")
        self.feedback = ttk.Label(footer, wraplength=390)
        self.feedback.pack(side="right")
        self.loaded = None
        self.privacy.bind("<<ComboboxSelected>>", lambda _event: self.apply_privacy())
        self.show()

    @staticmethod
    def choice(parent, row, label, values):
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", padx=(0, 12), pady=2)
        choice = ttk.Combobox(parent, values=list(values), state="readonly")
        choice.grid(row=row, column=1, sticky="ew", pady=2)
        return choice

    def _callback_error(self, _kind, _error, _traceback):
        self.feedback.configure(text="İşlem tamamlanamadı. Son kayıt korundu.")

    def guide(self):
        definitions = "\n\n".join(f"{label}\n{definition}" for label, definition in self.labels_and_definitions.values())
        messagebox.showinfo("Faz 3D etiket kılavuzu",
                            "Doğrudan: Yazar açıkça ifade ediyor.\n"
                            "Bağlamsal: Yorum metin tarafından destekleniyor.\n"
                            f"{self.context_guide}\n"
                            "Mahremiyet kararı uygun değilse konu etiketi kaydedilmez.\n\n" + definitions,
                            parent=self.root)

    @property
    def item(self):
        return self.items[self.state["position"]]

    def show_context(self):
        return self.item.cohort == "B"

    def heading_text(self):
        progress = review.review_progress(self.state)
        return (f"Kohort {self.item.cohort}  ·  Soru {self.state['position'] + 1}/{len(self.items)}"
                f"  ·  Kaydedilen A {progress['A'][0]}/{progress['A'][1]}"
                f"  ·  B {progress['B'][0]}/{progress['B'][1]}")

    def show(self):
        item = self.item
        decision = self.state["decisions"].get(item.review_id, {})
        self.question.configure(state="normal")
        self.question.delete("1.0", "end")
        self.question.insert("1.0", f"{item.title}\n\n{item.body}")
        self.question.configure(state="disabled")
        self.question.yview_moveto(0)
        self.privacy.set(review.PRIVACY.get(decision.get("privacy"), ""))
        self.b_choice.set(self.context_choices.get(decision.get("b_decision"), ""))
        for label, control in self.labels.items():
            control.set(review.EVIDENCE[decision.get("labels", {}).get(label, "none")])
        self.insufficient.set(decision.get("insufficient", False))
        self.apply_privacy()
        self.loaded = self.draft()
        self.heading.configure(text=self.heading_text())
        self.previous.configure(state="normal" if self.state["position"] else "disabled")
        self.next.configure(state="normal" if self.state["position"] < len(self.items) - 1 else "disabled")
        self.feedback.configure(text="Kaydedildi" if decision else "İnceleme bekliyor")

    def apply_privacy(self):
        suitable = self.privacy.get() == review.PRIVACY["suitable"]
        for control in self.labels.values():
            control.configure(state="readonly" if suitable else "disabled")
        self.b_choice.configure(state="readonly" if suitable and self.show_context() else "disabled")
        self.insufficient_control.configure(state="normal" if suitable else "disabled")

    @staticmethod
    def code(mapping, value):
        return next((key for key, label in mapping.items() if label == value), None)

    def draft(self):
        privacy = self.code(review.PRIVACY, self.privacy.get())
        suitable = privacy == "suitable"
        labels = {key: self.code(review.EVIDENCE, control.get()) for key, control in self.labels.items()
                  if suitable and control.get() != review.EVIDENCE["none"]}
        return {"privacy": privacy, "labels": labels, "insufficient": suitable and self.insufficient.get(),
                "b_decision": self.code(self.context_choices, self.b_choice.get())
                if suitable and self.show_context() else None}

    def save_current(self):
        decision = self.draft()
        try:
            self.validate(decision, self.item.cohort)
        except review.ReviewError as error:
            messages = {
                "choose_labels_or_insufficient_evidence": "Etiket seçin veya yetersiz kanıtı işaretleyin.",
                "choose_contextual_b_decision": "Kişisel belirsizlik için bağlamsal karar seçin.",
                "insufficient_evidence_requires_unclear_b": "Yetersiz kanıtta bağlamsal kararı belirsiz seçin.",
            }
            self.feedback.configure(text=messages.get(error.args[0], "Mahremiyet ve kanıt seçimini kontrol edin."))
            return
        key = self.item.review_id
        previous = self.state["decisions"].get(key)
        self.state["decisions"][key] = decision
        try:
            self.save()
        except Exception:
            if previous is None:
                self.state["decisions"].pop(key)
            else:
                self.state["decisions"][key] = previous
            self._callback_error(None, None, None)
            return
        self.show()

    def move(self, offset):
        if not self.confirm_discard():
            return
        position = self.state["position"]
        self.state["position"] = position + offset
        try:
            self.save()
        except Exception:
            self.state["position"] = position
            self._callback_error(None, None, None)
            return
        self.show()

    def confirm_discard(self):
        return self.draft() == self.loaded or messagebox.askyesno(
            "Kaydedilmemiş karar", "Bu sorudaki kaydedilmemiş seçimler bırakılsın mı?", parent=self.root
        )

    def close(self):
        if self.confirm_discard():
            self.root.quit()
