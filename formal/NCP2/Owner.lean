/-
Safety of the NCP 2 owner for every sequence of requests (spec 7.7, properties 1, 2, 3, and 6).

The theorems quantify over every request and every behavior of the application, so they hold for
any client, any network, and any fault that delivers frames to the owner, in any number of steps.
-/
import NCP2.Chain

namespace NCP2

variable (H : Frame → Id) (app : App)

/-- The owner invariant. Before `open`, nothing happened. After it, the log is a hash chain whose
last exchange is the kept one, `high` is its sequence number, `ended` says whether it ended the
session, and every accepted request belongs to the session and to protocol 2. -/
def Inv (o : Owner) : Prop :=
  (o.session = none ∧ o.log = [] ∧ o.kept = none) ∨
  (∃ s y, o.session = some s ∧ Chain H o.log y ∧ o.kept = some y ∧ o.high = y.request.seq ∧
    o.ended = decide (Ends y) ∧ ∀ x ∈ o.log, x.request.session = s ∧ x.request.protocol = 2)

variable {H app}

theorem inv_init : Inv H ({} : Owner) := Or.inl ⟨rfl, rfl, rfl⟩

theorem Chain.last_seq {xs : List Exchange} {y : Exchange} (hc : Chain H xs y) :
    y.request.seq + 1 = xs.length := by
  cases hc with
  | start _ _ _ hseq _ => simp [hseq]
  | extend xs y x _ hseq _ _ _ _ => simp [hseq]

theorem Chain.last_mem {xs : List Exchange} {y : Exchange} (hc : Chain H xs y) : y ∈ xs := by
  cases hc <;> simp

theorem execute_request (bound : Nat) (r : Request) (a : AppResult) :
    (execute H bound r a).request = H (.req r) := by
  unfold execute; split <;> rfl

theorem execute_not_rejected (bound : Nat) (r : Request) (a : AppResult) :
    (execute H bound r a).outcome ≠ .rejected := by
  unfold execute; split <;> simp [reply]

/-- The accepted step keeps the invariant. -/
theorem inv_accept {o : Owner} {s : Nat} {y : Exchange} {r : Request} {a : AppResult}
    (hs : o.session = some s) (hc : Chain H o.log y)
    (hh : o.high = y.request.seq) (he : o.ended = decide (Ends y))
    (hl : ∀ x ∈ o.log, x.request.session = s ∧ x.request.protocol = 2)
    (hseq : r.seq = o.high + 1) (hack : r.ack = some (H (.resp y.response)))
    (hop : r.op ≠ .openSession) (hlive : o.ended = false)
    (hsess : r.session = s) (hprot : r.protocol = 2) :
    Inv H (accept H o r a).1 := by
  refine Or.inr ⟨s, ⟨r, execute H o.bound r a⟩, hs, ?_, rfl, rfl, rfl, ?_⟩
  · refine Chain.extend _ y _ hc ?_ hack (execute_request _ _ _) hop ?_
    · have := hc.last_seq; show r.seq = o.log.length; omega
    · rw [he] at hlive; simpa using hlive
  · intro x hx
    simp only [accept, List.mem_append, List.mem_singleton] at hx
    rcases hx with hx | rfl
    · exact hl x hx
    · exact ⟨hsess, hprot⟩

/-- The checks of rules 7.3.6 to 7.3.11 keep the invariant. -/
theorem inv_checkThenAccept {o : Owner} {s : Nat} {y : Exchange} {r : Request} {a : AppResult}
    (hs : o.session = some s) (hc : Chain H o.log y)
    (hh : o.high = y.request.seq) (he : o.ended = decide (Ends y))
    (hl : ∀ x ∈ o.log, x.request.session = s ∧ x.request.protocol = 2)
    (hne : r.seq ≠ o.high) (hsess : r.session = s) (hprot : r.protocol = 2) (hinv : Inv H o) :
    Inv H (checkThenAccept H app o (some (H (.resp y.response))) r a).1 := by
  unfold checkThenAccept
  split
  · exact hinv
  split
  · exact hinv
  split
  · exact hinv
  rename_i hlt hgt hend
  split
  · exact hinv
  rename_i ack hack
  split
  · exact hinv
  rename_i hmatch
  have hack' : r.ack = some (H (.resp y.response)) := by
    rw [hack]; simp at hmatch; rw [hmatch]
  have hseq : r.seq = o.high + 1 := by omega
  have hlive : o.ended = false := by simpa using hend
  split
  · exact hinv
  · rename_i hop
    exact inv_accept hs hc hh he hl hseq hack' (by simp [hop]) hlive hsess hprot
  · rename_i name hop
    split
    · exact hinv
    split
    · exact hinv
    · exact inv_accept hs hc hh he hl hseq hack' (by simp [hop]) hlive hsess hprot

/-- Every step keeps the invariant. -/
theorem inv_step {o : Owner} (hinv : Inv H o) (r : Request) (a : AppResult) :
    Inv H (step H app o r a).1 := by
  unfold step
  split
  · exact hinv
  rename_i hprot
  have hprot : r.protocol = 2 := by simpa using hprot
  split
  · -- no session: section 7.1
    rename_i hnone
    unfold openStep
    split
    · rename_i hopen
      split
      · exact hinv
      rename_i hack
      split
      · refine Or.inr ⟨r.session, _, rfl, ?_, rfl, ?_, ?_, ?_⟩
        · exact Chain.start _ hopen.1 (by simpa using hack) hopen.2 rfl
        · simp [hopen.2]
        · simp [Ends, reply, hopen.1]
        · intro x hx; simp at hx; subst hx; exact ⟨rfl, hprot⟩
      all_goals exact hinv
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
        exact inv_checkThenAccept hs hc hh he hl hne hsess hprot hinv
    · rename_i hk'; rw [hk] at hk'; cases hk'

/-- The invariant holds after every sequence of requests from the initial owner. -/
theorem inv_run (inputs : List (Request × AppResult)) : Inv H (run H app {} inputs) := by
  suffices ∀ o, Inv H o → Inv H (run H app o inputs) from this _ inv_init
  induction inputs with
  | nil => intro o h; exact h
  | cons x rest ih => intro o h; exact ih _ (inv_step h x.1 x.2)

/-- Properties 1, 2, 3, and 7 for every sequence of requests: the accepted history is empty
before `open` and a hash chain after it. -/
theorem run_chain (inputs : List (Request × AppResult)) :
    (run H app {} inputs).log = [] ∨ ∃ y, Chain H (run H app {} inputs).log y := by
  rcases inv_run (H := H) (app := app) inputs with ⟨_, hl, _⟩ | ⟨_, y, _, hc, _⟩
  · exact Or.inl hl
  · exact Or.inr ⟨y, hc⟩

/-- Property 1: no request is executed twice, for every sequence of requests. -/
theorem run_at_most_once (inputs : List (Request × AppResult)) :
    ((run H app {} inputs).log.map (·.request)).Nodup := by
  rcases run_chain (H := H) (app := app) inputs with hl | ⟨y, hc⟩
  · simp [hl]
  · exact hc.requests_nodup

/-- A `rejected` response changes no state (rule 7.3, last paragraph). -/
theorem step_rejected {o : Owner} {r : Request} {a : AppResult}
    (h : (step H app o r a).2.outcome = .rejected) :
    (step H app o r a).1 = o := by
  revert h
  unfold step
  split
  · intro; rfl
  split
  · unfold openStep
    split
    · split
      · intro; rfl
      split
      · intro h; simp [reply] at h
      all_goals intro; rfl
    · intro; rfl
  · split
    · intro; rfl
    split
    · split
      · split <;> intro <;> rfl
      · unfold checkThenAccept
        repeat' split
        all_goals first
          | intro; rfl
          | intro h; exact absurd h (execute_not_rejected _ _ _)
    · unfold checkThenAccept
      repeat' split
      all_goals first
        | intro; rfl
        | intro h; exact absurd h (execute_not_rejected _ _ _)

/-- Rule 7.3.5: the kept request, sent again, gets the kept response again and changes nothing. -/
theorem step_retransmit {o : Owner} {k : Exchange} (hinv : Inv H o) (hk : o.kept = some k)
    (a : AppResult) : step H app o k.request a = (o, k.response) := by
  rcases hinv with ⟨_, _, hn⟩ | ⟨s, y, hs, hc, hk', hh, _, hl⟩
  · rw [hn] at hk; cases hk
  rw [hk] at hk'; cases hk'
  have ⟨hsess, hprot⟩ := hl k hc.last_mem
  unfold step
  simp [hprot, hs, hsess, hk, hh]

end NCP2
