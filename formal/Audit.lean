/-
Each claim of `Statements.lean`, proved from the library, with the axioms it uses.

The gate requires the printed axioms to be `propext`, `Classical.choice`, and `Quot.sound` only.
-/
import NCP2
import Statements

namespace NCP2.Audit

open NCP2 NCP2.Statements

theorem history_chain (H : Frame → Id) (app : App) (inputs : List (Request × Behavior)) :
    history H app inputs = [] ∨ ∃ y, Chain H (history H app inputs) y :=
  run_chain inputs

theorem atMostOnce : AtMostOnce := fun _ _ inputs => run_at_most_once inputs

theorem inOrder : InOrder := by
  intro H app inputs
  rcases history_chain H app inputs with h | ⟨y, hc⟩
  · simp [h]
  · exact hc.seqs

theorem acknowledged : Acknowledged := by
  intro H app inputs i h
  rcases history_chain H app inputs with h' | ⟨y, hc⟩
  · simp [h'] at h
  · exact hc.ack_index i h

theorem nothingAfterEnd : NothingAfterEnd := by
  intro H app inputs i h
  rcases history_chain H app inputs with h' | ⟨y, hc⟩
  · simp [h'] at h
  · exact hc.live_index i h

theorem rejectedChangesNothing : RejectedChangesNothing := fun _ _ _ _ _ h => step_rejected h

theorem retransmissionIdentical : RetransmissionIdentical := fun _ _ inputs _ a hk =>
  step_retransmit (inv_run inputs) hk a

theorem commitment : Commitment := by
  intro H app in₁ in₂ x₁ x₂ h₁ h₂ hinj hid
  rcases history_chain H app in₁ with e₁ | ⟨y₁, hc₁⟩
  · simp [e₁] at h₁
  rcases history_chain H app in₂ with e₂ | ⟨y₂, hc₂⟩
  · simp [e₂] at h₂
  rw [hc₁.getLast] at h₁; cases h₁
  rw [hc₂.getLast] at h₂; cases h₂
  exact hc₁.unique hc₂ hinj hid

theorem responsesOf_eq (H : Frame → Id) (app : App) :
    ∀ (o : Owner) (inputs : List (Request × Behavior)),
      OkIsOwnExecution.responsesOf H app o inputs = responses H app o inputs
  | _, [] => rfl
  | o, (r, a) :: rest => by
    simp [OkIsOwnExecution.responsesOf, responses, responsesOf_eq H app _ rest]

theorem historyFromInputs : HistoryFromInputs := by
  intro H app inputs x hx
  rcases run_log_sub (H := H) (app := app) (o := {}) inputs x hx with h | h
  · simp at h
  · exact h

theorem okIsOwnExecution : OkIsOwnExecution := by
  intro H app inputs r p hp hok hreq hinj
  rw [responsesOf_eq] at hp
  refine ok_is_own_execution inv_init inputs hp hok hreq fun q hq hqr => hinj q ?_ hqr
  obtain ⟨x, hx, rfl⟩ := List.mem_map.1 hq
  exact historyFromInputs H app inputs x hx

theorem rejectionMeansNeverExecuted : RejectionMeansNeverExecuted :=
  fun _ _ inputs r a hrej hcode => step_rejected_not_logged (inv_run inputs) r a hrej hcode

theorem staleMayHaveExecuted : StaleMayHaveExecuted :=
  fun H => ⟨_, _, _, _, seqStale_after_execution H⟩

theorem honestCalls_log (H : Frame → Id) (app : App) (s : Nat) :
    ∀ (calls : List (Nat × Nat × Behavior)) (o : Owner) (seq : Nat) (p : Response) (k : Exchange),
      o.session = some s → o.kept = some k → k.response = p → o.high + 1 = seq →
      o.ended = false →
      (∀ c ∈ calls, app.known c.1 = true ∧ c.2.2.valid = true ∧ ∃ v, c.2.2.result = .result v) →
      (honestCalls H app s o seq p calls).log.map (fun x => (x.request.op, x.request.body)) =
        o.log.map (fun x => (x.request.op, x.request.body)) ++
          calls.map (fun c => (Op.call c.1, c.2.1))
  | [], _, _, _, _, _, _, _, _, _, _ => by simp [honestCalls]
  | (name, body, b) :: rest, o, seq, p, k, hs, hk, hp, hh, hend, hcalls => by
    obtain ⟨hknown, hvalid, v, hres⟩ := hcalls (name, body, b) (by simp)
    subst hp
    have hstep := step_call (H := H) (app := app)
      (r := { protocol := 2, session := s, seq, op := .call name,
              ack := some (H (.resp k.response)), body })
      (b := b) hs hk hend rfl rfl hh.symm rfl rfl hknown hvalid hres
    have ih := honestCalls_log H app s rest
      { o with
        high := seq,
        kept := some ⟨{ protocol := 2, session := s, seq, op := .call name,
                        ack := some (H (.resp k.response)), body },
                      reply H { protocol := 2, session := s, seq, op := .call name,
                                ack := some (H (.resp k.response)), body } .ok none (.result v)⟩,
        ended := false,
        log := o.log ++ [⟨{ protocol := 2, session := s, seq, op := .call name,
                            ack := some (H (.resp k.response)), body },
                          reply H { protocol := 2, session := s, seq, op := .call name,
                                    ack := some (H (.resp k.response)), body } .ok none
                            (.result v)⟩] }
      (seq + 1)
      (reply H { protocol := 2, session := s, seq, op := .call name,
                 ack := some (H (.resp k.response)), body } .ok none (.result v))
      _ hs rfl rfl (by simp) rfl (fun c hc => hcalls c (by simp [hc]))
    simp only [honestCalls, hstep]
    rw [ih]
    simp

theorem faultFreeProgress : FaultFreeProgress := by
  intro H app s body bound b0 calls hopen hcalls r0
  have h0 := step_open (H := H) (app := app) (r := r0) (b := b0) rfl rfl rfl rfl hopen
  have ih := honestCalls_log H app s calls
    { session := some r0.session, bound, high := 0,
      kept := some ⟨r0, reply H r0 .ok none (.opened bound)⟩, ended := false,
      log := [⟨r0, reply H r0 .ok none (.opened bound)⟩] }
    1 (reply H r0 .ok none (.opened bound)) _ rfl rfl rfl rfl rfl hcalls
  rw [h0, ih]
  simp [r0]

end NCP2.Audit

#print axioms NCP2.Audit.atMostOnce
#print axioms NCP2.Audit.inOrder
#print axioms NCP2.Audit.acknowledged
#print axioms NCP2.Audit.nothingAfterEnd
#print axioms NCP2.Audit.rejectedChangesNothing
#print axioms NCP2.Audit.retransmissionIdentical
#print axioms NCP2.Audit.commitment
#print axioms NCP2.Audit.okIsOwnExecution
#print axioms NCP2.Audit.rejectionMeansNeverExecuted
#print axioms NCP2.Audit.staleMayHaveExecuted
#print axioms NCP2.Audit.historyFromInputs
#print axioms NCP2.Audit.faultFreeProgress
