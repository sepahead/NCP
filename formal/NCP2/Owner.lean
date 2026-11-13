/-
Safety of the NCP 2 owner for every sequence of inputs (spec 7.7, properties 1, 2, 3, and 8).

The theorems quantify over every request and every behavior of the application, so they hold for
any client, any network, and any fault that delivers frames to the owner, in any number of steps.
-/
import NCP2.Chain

namespace NCP2

variable (H : Frame → Id) (app : App)

/-- A response that the owner keeps: every response to an admitted request. Rejections, and the
two endings that admit nothing (`session_expired` and `shutdown`), are not kept. -/
def Keepable (p : Response) : Prop :=
  p.outcome ≠ .rejected ∧ p.code ≠ some .sessionExpired ∧ p.code ≠ some .shutdown

instance (p : Response) : Decidable (Keepable p) := by unfold Keepable; infer_instance

/-- The owner invariant. Before `open`, nothing happened. After it, the log is a hash chain whose
last exchange is the kept one, `high` is its sequence number, `ended` says whether it ended the
session, and every admitted request belongs to the session and to protocol 2 and got a keepable
response. -/
def Inv (o : Owner) : Prop :=
  (o.session = none ∧ o.log = [] ∧ o.kept = none) ∨
  (∃ s y, o.session = some s ∧ Chain H o.log y ∧ o.kept = some y ∧ o.high = y.request.seq ∧
    o.ended = decide (Ends y) ∧
    ∀ x ∈ o.log, x.request.session = s ∧ x.request.protocol = 2 ∧ Keepable x.response)

variable {H app}

theorem inv_init : Inv H ({} : Owner) := Or.inl ⟨rfl, rfl, rfl⟩

theorem Chain.last_seq {xs : List Exchange} {y : Exchange} (hc : Chain H xs y) :
    y.request.seq + 1 = xs.length := by
  cases hc with
  | start _ _ _ hseq _ => simp [hseq]
  | extend xs y x _ hseq _ _ _ _ => simp [hseq]

theorem Chain.last_mem {xs : List Exchange} {y : Exchange} (hc : Chain H xs y) : y ∈ xs := by
  cases hc <;> simp

theorem answer_request (bound : Nat) (r : Request) (b : Behavior) :
    (answer H app bound r b).request = H (.req r) := by
  unfold answer; repeat' split
  all_goals rfl

theorem answer_keepable (bound : Nat) (r : Request) (b : Behavior) :
    Keepable (answer H app bound r b) := by
  unfold answer Keepable; repeat' split
  all_goals simp [reply]

/-- Stopping changes only the `stopped` flag, so it keeps the invariant. -/
theorem inv_stop {o : Owner} (hinv : Inv H o) : Inv H { o with stopped := true } := by
  rcases hinv with ⟨hn, hl, hk⟩ | ⟨s, y, hs, hc, hk, hh, he, hl⟩
  · exact Or.inl ⟨hn, hl, hk⟩
  · exact Or.inr ⟨s, y, hs, hc, hk, hh, he, hl⟩

/-- The admitted step keeps the invariant. -/
theorem inv_admit {o : Owner} {s : Nat} {y : Exchange} {r : Request} {b : Behavior}
    (hs : o.session = some s) (hc : Chain H o.log y)
    (hh : o.high = y.request.seq) (he : o.ended = decide (Ends y))
    (hl : ∀ x ∈ o.log, x.request.session = s ∧ x.request.protocol = 2 ∧ Keepable x.response)
    (hseq : r.seq = o.high + 1) (h_ack : r.ack = some (H (.resp y.response)))
    (hop : r.op ≠ .openSession) (hlive : o.ended = false)
    (hsess : r.session = s) (hprot : r.protocol = 2) :
    Inv H (admit o r (answer H app o.bound r b)).1 := by
  refine Or.inr ⟨s, ⟨r, answer H app o.bound r b⟩, hs, ?_, rfl, rfl, rfl, ?_⟩
  · refine Chain.extend _ y _ hc ?_ h_ack (answer_request _ _ _) hop ?_
    · have := hc.last_seq; show r.seq = o.log.length; omega
    · rw [he] at hlive; simpa using hlive
  · intro x hx
    simp only [admit, List.mem_append, List.mem_singleton] at hx
    rcases hx with hx | rfl
    · exact hl x hx
    · exact ⟨hsess, hprot, answer_keepable _ _ _⟩

/-- The checks of rules 7.3.6 to 7.3.10 keep the invariant. -/
theorem inv_checkThenAdmit {o : Owner} {s : Nat} {y : Exchange} {r : Request} {b : Behavior}
    (hs : o.session = some s) (hc : Chain H o.log y)
    (hh : o.high = y.request.seq) (he : o.ended = decide (Ends y))
    (hl : ∀ x ∈ o.log, x.request.session = s ∧ x.request.protocol = 2 ∧ Keepable x.response)
    (hne : r.seq ≠ o.high) (hsess : r.session = s) (hprot : r.protocol = 2) (hinv : Inv H o) :
    Inv H (checkThenAdmit H app o (some (H (.resp y.response))) r b).1 := by
  unfold checkThenAdmit
  split
  · exact hinv
  split
  · exact hinv
  split
  · exact hinv
  rename_i hlt hgt hend
  split
  · exact hinv
  rename_i ack h_ack
  split
  · exact hinv
  rename_i hmatch
  have h_ack' : r.ack = some (H (.resp y.response)) := by
    rw [h_ack]; simp at hmatch; rw [hmatch]
  have hseq : r.seq = o.high + 1 := by omega
  have hlive : o.ended = false := by simpa using hend
  split
  · exact hinv
  rename_i hop
  split
  · exact hinv
  · exact inv_admit hs hc hh he hl hseq h_ack' hop hlive hsess hprot

/-- Every step keeps the invariant. -/
theorem inv_step {o : Owner} (hinv : Inv H o) (r : Request) (b : Behavior) :
    Inv H (step H app o r b).1 := by
  unfold step
  split
  · exact hinv
  rename_i hprot
  have hprot : r.protocol = 2 := by simpa using hprot
  split
  · -- no session: section 7.1 and rule 7.3.3
    unfold openStep
    split
    · rename_i hseq0
      split
      · rename_i hopen
        split
        · exact hinv
        rename_i h_ack
        split
        · rename_i bd _
          split
          · exact hinv
          · refine Or.inr ⟨r.session, _, rfl, ?_, rfl, ?_, ?_, ?_⟩
            · exact Chain.start _ hopen (by simpa using h_ack) hseq0 rfl
            · simp [hseq0]
            · simp [Ends, reply, hopen]
            · intro x hx; simp at hx; subst hx; exact ⟨rfl, hprot, by simp [Keepable, reply]⟩
        all_goals exact hinv
      · exact hinv
    · exact hinv
  · rename_i s hs
    split
    · exact hinv
    rename_i hsess
    have hsess : r.session = s := by simpa using hsess
    rcases hinv with ⟨hn, _, _⟩ | ⟨s', y, hs', hc, hk, hh, he, hl⟩
    · rw [hn] at hs; cases hs
    rw [hs] at hs'; cases hs'
    have hinv : Inv H o := Or.inr ⟨s, y, hs, hc, hk, hh, he, hl⟩
    split
    · rename_i k hk'
      rw [hk] at hk'; cases hk'
      split
      · split <;> exact hinv
      · rename_i hne
        exact inv_checkThenAdmit hs hc hh he hl hne hsess hprot hinv
    · rename_i hk'; rw [hk] at hk'; cases hk'

theorem inv_apply {o : Owner} (hinv : Inv H o) (i : Input) : Inv H (apply H app o i) := by
  cases i with
  | req r b => exact inv_step hinv r b
  | stop => exact inv_stop hinv

theorem inv_run_from {o : Owner} (hinv : Inv H o) (inputs : List Input) :
    Inv H (run H app o inputs) := by
  induction inputs generalizing o with
  | nil => exact hinv
  | cons i rest ih => exact ih (inv_apply hinv i)

/-- The invariant holds after every sequence of inputs from the initial owner. -/
theorem inv_run (inputs : List Input) : Inv H (run H app {} inputs) :=
  inv_run_from inv_init inputs

/-- Properties 1, 2, 3, and 8 for every sequence of inputs: the admitted history is empty before
`open` and a hash chain after it. -/
theorem run_chain (inputs : List Input) :
    (run H app {} inputs).log = [] ∨ ∃ y, Chain H (run H app {} inputs).log y := by
  rcases inv_run (H := H) (app := app) inputs with ⟨_, hl, _⟩ | ⟨_, y, _, hc, _⟩
  · exact Or.inl hl
  · exact Or.inr ⟨y, hc⟩

/-- Property 1: no request is admitted twice, for every sequence of inputs. -/
theorem run_at_most_once (inputs : List Input) :
    ((run H app {} inputs).log.map (·.request)).Nodup := by
  rcases run_chain (H := H) (app := app) inputs with hl | ⟨y, hc⟩
  · simp [hl]
  · exact hc.requests_nodup

/-- A `rejected` response changes no state (rule 7.3, after the rules). -/
theorem step_rejected {o : Owner} {r : Request} {b : Behavior}
    (h : (step H app o r b).2.outcome = .rejected) :
    (step H app o r b).1 = o := by
  revert h
  unfold step
  split
  · intro; rfl
  split
  · unfold openStep
    repeat' split
    all_goals first
      | intro; rfl
      | intro h; simp [reply] at h
  · split
    · intro; rfl
    split
    · split
      · split <;> intro <;> rfl
      · unfold checkThenAdmit admit
        repeat' split
        all_goals first
          | intro; rfl
          | intro h; exact absurd h (answer_keepable _ _ _).1
          | intro h; simp [reply] at h
    · unfold checkThenAdmit admit
      repeat' split
      all_goals first
        | intro; rfl
        | intro h; exact absurd h (answer_keepable _ _ _).1
        | intro h; simp [reply] at h

/-- Rule 7.3.5: the kept request, sent again, gets the kept response again and changes nothing. -/
theorem step_retransmit {o : Owner} {k : Exchange} (hinv : Inv H o) (hk : o.kept = some k)
    (b : Behavior) : step H app o k.request b = (o, k.response) := by
  rcases hinv with ⟨_, _, hn⟩ | ⟨s, y, hs, hc, hk', hh, _, hl⟩
  · rw [hn] at hk; cases hk
  rw [hk] at hk'; cases hk'
  have ⟨hsess, hprot, _⟩ := hl k hc.last_mem
  unfold step
  simp [hprot, hs, hsess, hk, hh]

/-- Once the owner stops, it stays stopped and admits nothing: every later state keeps the log. -/
theorem stopped_step {o : Owner} (hstop : o.stopped = true) (r : Request) (b : Behavior) :
    (step H app o r b).1.stopped = true ∧ (step H app o r b).1.log = o.log := by
  unfold step
  split
  · exact ⟨hstop, rfl⟩
  split
  · unfold openStep
    repeat' split
    all_goals first
      | exact ⟨hstop, rfl⟩
      | simp_all
  · split
    · exact ⟨hstop, rfl⟩
    split
    · split
      · split <;> exact ⟨hstop, rfl⟩
      · unfold checkThenAdmit
        repeat' split
        all_goals first
          | exact ⟨hstop, rfl⟩
          | simp_all
    · unfold checkThenAdmit
      repeat' split
      all_goals first
        | exact ⟨hstop, rfl⟩
        | simp_all

theorem stopped_run {o : Owner} (hstop : o.stopped = true) (inputs : List Input) :
    (run H app o inputs).stopped = true ∧ (run H app o inputs).log = o.log := by
  induction inputs generalizing o with
  | nil => exact ⟨hstop, rfl⟩
  | cons i rest ih =>
    cases i with
    | req r b =>
      have ⟨h1, h2⟩ := stopped_step (H := H) (app := app) hstop r b
      have ⟨h3, h4⟩ := ih h1
      exact ⟨h3, h4.trans h2⟩
    | stop =>
      have ⟨h3, h4⟩ := ih (o := { o with stopped := true }) rfl
      exact ⟨h3, h4⟩

end NCP2
