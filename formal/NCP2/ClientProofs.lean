/-
What the verdicts of a client that follows section 7.6 mean (spec 7.7, property 7).

Three theorems are about the client alone: at most one verdict is "possibly executed", and it is
the last; every other verdict comes from a response that names the request; and the verdict
"rejected" belongs only to `open` (rule 7.6.4). The composed theorem `client_truthful` joins them
with the owner's theorems: if every response that the client accepts is one that the owner sent,
each verdict "executed" and "not executed" is true in the owner's history, then and at every later
time.
-/
import NCP2.Client
import NCP2.ClientModel

namespace NCP2

variable {H : Frame → Id}

/-- The client invariant: an ended client has no outstanding request; an unknown verdict is the
last one and ends the client; and no verdict before the last is unknown. -/
def CInv (c : Client) : Prop :=
  (c.ended = true → c.pending = none) ∧
  (∀ x ∈ c.verdicts.getLast?, x.2.1 = .unknown → c.ended = true) ∧
  (∀ (i : Nat) (h : i + 1 < c.verdicts.length), (c.verdicts[i]'(by omega)).2.1 ≠ .unknown)

theorem cinv_append {c : Client} (hinv : CInv c) {r : Request} (hp : c.pending = some r)
    (x : Record) :
    ∀ (i : Nat) (h : i + 1 < (c.verdicts ++ [x]).length),
      ((c.verdicts ++ [x])[i]'(by omega)).2.1 ≠ .unknown := by
  intro i h
  have hnot : c.ended = false := by
    cases hend : c.ended
    · rfl
    · rw [hinv.1 hend] at hp; cases hp
  simp only [List.length_append, List.length_singleton] at h
  rw [List.getElem_append_left (by omega)]
  by_cases hi : i + 1 < c.verdicts.length
  · exact hinv.2.2 i hi
  · have hlast : c.verdicts.getLast? = some (c.verdicts[i]'(by omega)) := by
      rw [List.getLast?_eq_getElem?]; simp [show c.verdicts.length - 1 = i by omega]
    intro hu
    have := hinv.2.1 _ hlast hu
    rw [hnot] at this; cases this

theorem cinv_step {c : Client} (hinv : CInv c) (e : ClientEvent) : CInv (clientStep H c e) := by
  cases e with
  | send op body =>
    simp only [clientStep]
    split
    · exact hinv
    rename_i hfree
    have hnot : c.ended = false := by
      cases hend : c.ended
      · rfl
      · simp [hend] at hfree
    split
    · split
      · exact hinv
      · exact ⟨fun h => by simp_all, fun x hx hu => by simpa using hinv.2.1 x hx hu, hinv.2.2⟩
    · split
      · exact ⟨fun h => by simp_all, fun x hx hu => by simpa using hinv.2.1 x hx hu, hinv.2.2⟩
      · exact hinv
  | receive p =>
    simp only [clientStep]
    split
    · exact hinv
    rename_i r hp
    split
    · split
      · refine ⟨fun _ => rfl, ?_, cinv_append hinv hp _⟩
        intro x hx hu; simp at hx; subst hx; cases hu
      · refine ⟨fun _ => rfl, ?_, cinv_append hinv hp _⟩
        intro x hx hu; simp at hx; subst hx; cases hu
      · split
        · refine ⟨fun _ => rfl, ?_, cinv_append hinv hp _⟩
          intro x hx hu; simp at hx; subst hx; cases hu
        · exact ⟨fun _ => rfl, fun _ _ _ => rfl, cinv_append hinv hp _⟩
      · exact ⟨fun _ => rfl, fun _ _ _ => rfl, cinv_append hinv hp _⟩
    · exact hinv
  | timeout =>
    simp only [clientStep]
    split
    · exact hinv
    rename_i r hp
    exact ⟨fun _ => rfl, fun _ _ _ => rfl, cinv_append hinv hp _⟩

theorem cinv_run {c : Client} (hinv : CInv c) (events : List ClientEvent) :
    CInv (clientRun H c events) := by
  induction events generalizing c with
  | nil => exact hinv
  | cons e rest ih => exact ih (cinv_step hinv e)

/-- Property 7, first part: at most one verdict of a session is "possibly executed", and it is the
last one. -/
theorem unknown_is_last (s : Nat) (events : List ClientEvent) :
    ∀ (i : Nat) (h : i + 1 < (clientRun H { session := s } events).verdicts.length),
      ((clientRun H { session := s } events).verdicts[i]'(by omega)).2.1 ≠ .unknown :=
  (cinv_run (H := H) (c := { session := s })
    ⟨fun h => by simp at h, fun x hx => by simp at hx, fun i h => by simp at h⟩ events).2.2

/-- Every verdict that is not "possibly executed" comes from a response that arrived and names the
request, and the verdict is the one of that response. -/
theorem verdict_evidence (c : Client) (events : List ClientEvent)
    (hc : ∀ x ∈ c.verdicts, x.2.1 ≠ .unknown →
      ∃ p, x.2.2 = some p ∧ p.request = H (.req x.1) ∧ verdictOf p = x.2.1) :
    ∀ x ∈ (clientRun H c events).verdicts, x.2.1 ≠ .unknown →
      ∃ p, x.2.2 = some p ∧ p.request = H (.req x.1) ∧ verdictOf p = x.2.1 ∧
        (x ∈ c.verdicts ∨ p ∈ received events) := by
  induction events generalizing c with
  | nil =>
    intro x hx hu
    obtain ⟨p, h1, h2, h3⟩ := hc x hx hu
    exact ⟨p, h1, h2, h3, Or.inl hx⟩
  | cons e rest ih =>
    have hstep : ∀ x ∈ (clientStep H c e).verdicts, x.2.1 ≠ .unknown →
        ∃ p, x.2.2 = some p ∧ p.request = H (.req x.1) ∧ verdictOf p = x.2.1 ∧
          (x ∈ c.verdicts ∨ p ∈ received [e]) := by
      intro x hx hu
      cases e with
      | send op body =>
        have hsame : (clientStep H c (.send op body)).verdicts = c.verdicts := by
          simp only [clientStep]; repeat' split
          all_goals rfl
        rw [hsame] at hx
        obtain ⟨p, h1, h2, h3⟩ := hc x hx hu
        exact ⟨p, h1, h2, h3, Or.inl hx⟩
      | timeout =>
        simp only [clientStep] at hx
        split at hx
        · obtain ⟨p, h1, h2, h3⟩ := hc x hx hu
          exact ⟨p, h1, h2, h3, Or.inl hx⟩
        · simp only [List.mem_append, List.mem_singleton] at hx
          rcases hx with hx | rfl
          · obtain ⟨p, h1, h2, h3⟩ := hc x hx hu
            exact ⟨p, h1, h2, h3, Or.inl hx⟩
          · exact absurd rfl hu
      | receive p =>
        simp only [clientStep] at hx
        split at hx
        · obtain ⟨q, h1, h2, h3⟩ := hc x hx hu
          exact ⟨q, h1, h2, h3, Or.inl hx⟩
        rename_i r _
        split at hx
        · rename_i hm
          split at hx
          all_goals (try split at hx)
          all_goals
            simp only [List.mem_append, List.mem_singleton] at hx
            rcases hx with hx | rfl
            · obtain ⟨q, h1, h2, h3⟩ := hc x hx hu
              exact ⟨q, h1, h2, h3, Or.inl hx⟩
            · first
                | exact absurd rfl hu
                | refine ⟨p, rfl, hm.2.2, ?_, Or.inr (by simp [received])⟩
                  simp only [verdictOf]
                  try (split <;> simp_all)
        · obtain ⟨q, h1, h2, h3⟩ := hc x hx hu
          exact ⟨q, h1, h2, h3, Or.inl hx⟩
    intro x hx hu
    obtain ⟨p, h1, h2, h3, h4⟩ := ih (clientStep H c e)
      (fun y hy hyu => by
        obtain ⟨q, k1, k2, k3, _⟩ := hstep y hy hyu
        exact ⟨q, k1, k2, k3⟩) x hx hu
    refine ⟨p, h1, h2, h3, ?_⟩
    rcases h4 with h4 | h4
    · obtain ⟨q, k1, _, _, k4⟩ := hstep x h4 hu
      rcases k4 with k4 | k4
      · exact Or.inl k4
      · rw [h1] at k1; cases k1
        right; cases e <;> simp_all [received]
    · right; cases e <;> simp_all [received]

/-- Rule 7.6.4: the verdict "rejected" belongs only to `open`. -/
theorem rejected_only_open_run (c : Client) (events : List ClientEvent)
    (hc : ∀ x ∈ c.verdicts, x.2.1 = .rejected → x.1.op = .openSession) :
    ∀ x ∈ (clientRun H c events).verdicts, x.2.1 = .rejected → x.1.op = .openSession := by
  induction events generalizing c with
  | nil => exact hc
  | cons e rest ih =>
    apply ih
    intro x hx hrej
    cases e with
    | send op body =>
      have hsame : (clientStep H c (.send op body)).verdicts = c.verdicts := by
        simp only [clientStep]; repeat' split
        all_goals rfl
      rw [hsame] at hx
      exact hc x hx hrej
    | timeout =>
      simp only [clientStep] at hx
      split at hx
      · exact hc x hx hrej
      · simp only [List.mem_append, List.mem_singleton] at hx
        rcases hx with hx | rfl
        · exact hc x hx hrej
        · cases hrej
    | receive p =>
      simp only [clientStep] at hx
      split at hx
      · exact hc x hx hrej
      split at hx
      · split at hx
        all_goals (try split at hx)
        all_goals
          simp only [List.mem_append, List.mem_singleton] at hx
          rcases hx with hx | rfl
          · exact hc x hx hrej
          · first
              | assumption
              | (simp at hrej; done)
              | (simp only [verdictOf] at hrej; split at hrej <;> simp_all)
      · exact hc x hx hrej

/-- Rule 7.6.4: a client that follows section 7.6 has the verdict "rejected" only for `open`. -/
theorem rejected_only_open (s : Nat) (events : List ClientEvent) :
    ∀ x ∈ (clientRun H { session := s } events).verdicts, x.2.1 = .rejected →
      x.1.op = .openSession :=
  rejected_only_open_run { session := s } events (fun x hx => by simp at hx)

theorem verdictOf_ran {p : Response} (h : verdictOf p = .ran) :
    p.outcome = .ok ∨ (p.outcome = .ended ∧ p.code = some .resultTooLarge) := by
  revert h; unfold verdictOf
  split <;> simp_all

theorem verdictOf_notRun {p : Response} (h : verdictOf p = .notRun) :
    p.outcome = .declined ∨ (p.outcome = .ended ∧ p.code = some .shutdown) := by
  revert h; unfold verdictOf
  split <;> simp_all

/-- Property 7: every verdict "executed" and "not executed" of a client that follows section 7.6 is
true in the owner's history, then and at every later time, if every response that the client
accepts is one that the owner sent, and no request of the owner's inputs shares the identity of a
request of the client's verdicts unless it is that request. -/
theorem client_truthful (app : App) (s : Nat) (events : List ClientEvent)
    (inputs more : List Input)
    (hrecv : ∀ p ∈ received events, p ∈ responses H app {} inputs)
    (hinj : ∀ x ∈ (clientRun H { session := s } events).verdicts,
      ∀ q ∈ requests (inputs ++ more), H (.req q) = H (.req x.1) → q = x.1) :
    ∀ x ∈ (clientRun H { session := s } events).verdicts,
      (x.2.1 = .ran → ∃ y ∈ (run H app {} (inputs ++ more)).log, y.request = x.1 ∧ Executed y ∧
        ∀ z ∈ (run H app {} (inputs ++ more)).log, z.request = x.1 → z = y) ∧
      (x.2.1 = .notRun → ∀ y ∈ (run H app {} (inputs ++ more)).log, y.request = x.1 →
        ¬ Executed y) := by
  intro x hx
  have hev := verdict_evidence (H := H) { session := s } events (fun y hy => by simp at hy)
  have hlog : ∀ q ∈ (run H app {} (inputs ++ more)).log.map (·.request),
      H (.req q) = H (.req x.1) → q = x.1 := by
    intro q hq hqh
    obtain ⟨y, hy, rfl⟩ := List.mem_map.1 hq
    rcases run_log_sub (H := H) (app := app) (o := {}) (inputs ++ more) y hy with h | h
    · simp at h
    · exact hinj x hx _ h hqh
  constructor
  · intro hran
    obtain ⟨p, _, hreq, hv, hsrc⟩ := hev x hx (by rw [hran]; decide)
    rcases hsrc with hsrc | hsrc
    · simp at hsrc
    have hp := hrecv p hsrc
    rw [hran] at hv
    rcases verdictOf_ran hv with ho | ⟨ho, hc⟩
    · obtain ⟨y, hy, hyr, hyp, huniq⟩ :=
        kept_is_final inv_init inputs more hp (responses_keepable inv_init inputs hp (Or.inl ho)) hreq hlog
      exact ⟨y, hy, hyr, by simp [Executed, hyp, ho], huniq⟩
    · have hk : Keepable p := by simp [Keepable, ho, hc]
      obtain ⟨y, hy, hyr, hyp, huniq⟩ := kept_is_final inv_init inputs more hp hk hreq hlog
      exact ⟨y, hy, hyr, by simp [Executed, hyp, ho], huniq⟩
  · intro hnot y hy hyr
    obtain ⟨p, _, hreq, hv, hsrc⟩ := hev x hx (by rw [hnot]; decide)
    rcases hsrc with hsrc | hsrc
    · simp at hsrc
    have hp := hrecv p hsrc
    rw [hnot] at hv
    rcases verdictOf_notRun hv with ho | ⟨_, hc⟩
    · exact declined_is_final inv_init inputs more hp ho hreq hlog y hy hyr
    · have hnotin := shutdown_is_final inv_init inputs more hp hc hreq
        (fun q hq hqh => hinj x hx q hq hqh)
      exact absurd (List.mem_map.2 ⟨y, hy, hyr⟩) hnotin

end NCP2
