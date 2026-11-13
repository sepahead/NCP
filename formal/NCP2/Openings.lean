/-
Openings and their nonces (spec 7.1 and 7.7, property 1, assumption A4).

The first exchange of every history is the acceptance of an `open` input, and its response carries
the nonce of that input. So two runs whose `open` inputs have different nonces have different first
responses, and `Chain.shared_prefix` then shows that they admit no common request after `open`.
-/
import NCP2.Client

namespace NCP2

variable {H : Frame → Id} {app : App}

/-- A step that starts the history from an empty one accepts an `open`, and the response carries
the nonce of the step's behavior. -/
theorem step_head {o : Owner} (hinv : Inv H o) (hempty : o.log = []) (r : Request) (b : Behavior)
    (x : Exchange) (hx : (step H app o r b).1.log.head? = some x) :
    x.request = r ∧ r.op = .openSession ∧
      ∃ bd, x.response = reply H r .ok none (.opened bd b.nonce) := by
  have hnone : o.session = none := by
    rcases hinv with ⟨hs, _, _⟩ | ⟨s, y, _, hc, _⟩
    · exact hs
    · exact absurd hempty hc.ne_nil
  unfold step at hx
  split at hx
  · simp [hempty] at hx
  rw [hnone] at hx
  simp only at hx
  unfold openStep at hx
  split at hx
  · split at hx
    · split at hx
      · simp [hempty] at hx
      · split at hx
        · split at hx
          · simp [hempty] at hx
          · simp only [List.head?_cons, Option.some.injEq] at hx
            subst hx
            rename_i hop _ _ bd _ _
            exact ⟨rfl, hop, bd, rfl⟩
        all_goals simp [hempty] at hx
    · simp [hempty] at hx
  · simp [hempty] at hx

/-- The first exchange of a history either was there before, or is the acceptance of an `open`
input whose nonce its response carries. -/
theorem run_head {o : Owner} (hinv : Inv H o) (inputs : List Input) (x : Exchange)
    (hx : (run H app o inputs).log.head? = some x) :
    o.log.head? = some x ∨
      ∃ r b bd, Input.req r b ∈ inputs ∧ r.op = .openSession ∧ x.request = r ∧
        x.response = reply H r .ok none (.opened bd b.nonce) := by
  induction inputs generalizing o with
  | nil => exact Or.inl hx
  | cons i rest ih =>
    rcases ih (inv_apply hinv i) hx with h | ⟨r, b, bd, hmem, hop, hreq, hresp⟩
    · cases i with
      | req r b =>
        by_cases hempty : o.log = []
        · obtain ⟨hreq, hop, bd, hresp⟩ := step_head hinv hempty r b x h
          exact Or.inr ⟨r, b, bd, by simp, hop, hreq, hresp⟩
        · obtain ⟨t, ht⟩ := step_log_prefix (H := H) (app := app) hinv r b
          left
          rw [← h]
          show o.log.head? = (step H app o r b).1.log.head?
          rw [← ht]
          cases hl : o.log with
          | nil => exact absurd hl hempty
          | cons a l => rfl
      | stop => exact Or.inl h
    · exact Or.inr ⟨r, b, bd, List.mem_cons_of_mem _ hmem, hop, hreq, hresp⟩

/-- The first exchange of every history from a new owner is the acceptance of an `open` input,
and its response body carries the nonce of that input. -/
theorem history_head (inputs : List Input) (x : Exchange)
    (hx : (run H app {} inputs).log.head? = some x) :
    ∃ r b bd, Input.req r b ∈ inputs ∧ r.op = .openSession ∧ x.request = r ∧
      x.response.body = .opened bd b.nonce := by
  rcases run_head (H := H) (app := app) inv_init inputs x hx with h | ⟨r, b, bd, hmem, hop, hreq, hresp⟩
  · simp at h
  · exact ⟨r, b, bd, hmem, hop, hreq, by rw [hresp]; rfl⟩

end NCP2
