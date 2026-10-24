/-
The claims, without proofs. Review this file: it is what the proofs establish.

`Audit.lean` checks that each proved theorem has exactly the type stated here, and prints the
axioms that it uses. A change to a claim must change this file.
-/
import NCP2.Model

namespace NCP2.Statements

open NCP2

/-- The accepted exchanges after any sequence of requests from a new owner. -/
def history (H : Frame → Id) (app : App) (inputs : List (Request × AppResult)) : List Exchange :=
  (run H app {} inputs).log

/-- 7.7.1: no request is executed twice. -/
def AtMostOnce : Prop :=
  ∀ (H : Frame → Id) (app : App) (inputs : List (Request × AppResult)),
    ((history H app inputs).map (·.request)).Nodup

/-- 7.7.2: the accepted requests carry the sequence numbers 0, 1, 2, ... in order. -/
def InOrder : Prop :=
  ∀ (H : Frame → Id) (app : App) (inputs : List (Request × AppResult)),
    (history H app inputs).map (·.request.seq) = List.range (history H app inputs).length

/-- 7.7.3: each accepted request after `open` acknowledges the identity of the response before it. -/
def Acknowledged : Prop :=
  ∀ (H : Frame → Id) (app : App) (inputs : List (Request × AppResult)) (i : Nat)
    (h : i + 1 < (history H app inputs).length),
    ((history H app inputs)[i + 1]).request.ack =
      some (H (.resp ((history H app inputs)[i]).response))

/-- 7.3.8 and 7.7: nothing is accepted after an exchange that ends the session. -/
def NothingAfterEnd : Prop :=
  ∀ (H : Frame → Id) (app : App) (inputs : List (Request × AppResult)) (i : Nat)
    (h : i + 1 < (history H app inputs).length), ¬ Ends ((history H app inputs)[i])

/-- 7.3: a `rejected` response changes no state. -/
def RejectedChangesNothing : Prop :=
  ∀ (H : Frame → Id) (app : App) (o : Owner) (r : Request) (a : AppResult),
    (step H app o r a).2.outcome = .rejected → (step H app o r a).1 = o

/-- 7.3.5: the kept request, sent again, gets the kept response again and changes nothing. -/
def RetransmissionIdentical : Prop :=
  ∀ (H : Frame → Id) (app : App) (inputs : List (Request × AppResult)) (k : Exchange) (a : AppResult),
    (run H app {} inputs).kept = some k →
      step H app (run H app {} inputs) k.request a = (run H app {} inputs, k.response)

/-- The frames of a history. -/
def framesOf (xs : List Exchange) : List Frame :=
  xs.flatMap fun x => [.req x.request, .resp x.response]

/-- 7.7.6: if the digest has no collision among the frames of two histories, equal identities of
their last responses imply equal histories. -/
def Commitment : Prop :=
  ∀ (H : Frame → Id) (app : App) (in₁ in₂ : List (Request × AppResult)) (x₁ x₂ : Exchange),
    (history H app in₁).getLast? = some x₁ → (history H app in₂).getLast? = some x₂ →
    (∀ f ∈ framesOf (history H app in₁), ∀ g ∈ framesOf (history H app in₂), H f = H g → f = g) →
    H (.resp x₁.response) = H (.resp x₂.response) → history H app in₁ = history H app in₂

/-- 7.7.4: an `ok` response that the owner sent and that names the identity of a request `r` is the
response of exactly one execution of `r`, if no other request frame shares `r`'s identity. -/
def OkIsOwnExecution : Prop :=
  ∀ (H : Frame → Id) (app : App) (inputs : List (Request × AppResult)) (r : Request) (p : Response),
    p ∈ responsesOf H app {} inputs → p.outcome = .ok → p.request = H (.req r) →
    (∀ q, H (.req q) = H (.req r) → q = r) →
    ∃ x ∈ history H app inputs, x.request = r ∧ x.response = p ∧
      ∀ y ∈ history H app inputs, y.request = r → y = x
where
  /-- The responses that the owner sends during a sequence of requests. -/
  responsesOf (H : Frame → Id) (app : App) (o : Owner) : List (Request × AppResult) → List Response
    | [] => []
    | (r, a) :: rest => (step H app o r a).2 :: responsesOf H app (step H app o r a).1 rest

/-- 7.5: every rejection except `seq_stale` means that the owner has never executed the request. -/
def RejectionMeansNeverExecuted : Prop :=
  ∀ (H : Frame → Id) (app : App) (inputs : List (Request × AppResult)) (r : Request) (a : AppResult),
    (step H app (run H app {} inputs) r a).2.outcome = .rejected →
    (step H app (run H app {} inputs) r a).2.code ≠ some .seqStale →
    r ∉ (history H app inputs).map (·.request)

/-- 7.5: `seq_stale` can answer a request that executed earlier. -/
def StaleMayHaveExecuted : Prop :=
  ∃ (H : Frame → Id) (app : App) (inputs : List (Request × AppResult)) (r : Request) (a : AppResult),
    (step H app (run H app {} inputs) r a).2.code = some .seqStale ∧
    r ∈ (history H app inputs).map (·.request)

end NCP2.Statements
