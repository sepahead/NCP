/-
The claims, without proofs. Review this file: it is what the proofs establish.

`Audit.lean` checks that each proved theorem has exactly the type stated here, and prints the
axioms that it uses. A change to a claim must change this file.
-/
import NCP2.Model

namespace NCP2.Statements

open NCP2

/-- The accepted exchanges after any sequence of requests from a new owner. -/
def history (H : Frame → Id) (app : App) (inputs : List (Request × Behavior)) : List Exchange :=
  (run H app {} inputs).log

/-- 7.7.1: no request is executed twice. -/
def AtMostOnce : Prop :=
  ∀ (H : Frame → Id) (app : App) (inputs : List (Request × Behavior)),
    ((history H app inputs).map (·.request)).Nodup

/-- 7.7.2: the accepted requests carry the sequence numbers 0, 1, 2, ... in order. -/
def InOrder : Prop :=
  ∀ (H : Frame → Id) (app : App) (inputs : List (Request × Behavior)),
    (history H app inputs).map (·.request.seq) = List.range (history H app inputs).length

/-- 7.7.3: each accepted request after `open` acknowledges the identity of the response before it. -/
def Acknowledged : Prop :=
  ∀ (H : Frame → Id) (app : App) (inputs : List (Request × Behavior)) (i : Nat)
    (h : i + 1 < (history H app inputs).length),
    ((history H app inputs)[i + 1]).request.ack =
      some (H (.resp ((history H app inputs)[i]).response))

/-- 7.3.8 and 7.7: nothing is accepted after an exchange that ends the session. -/
def NothingAfterEnd : Prop :=
  ∀ (H : Frame → Id) (app : App) (inputs : List (Request × Behavior)) (i : Nat)
    (h : i + 1 < (history H app inputs).length), ¬ Ends ((history H app inputs)[i])

/-- 7.3: a `rejected` response changes no state. -/
def RejectedChangesNothing : Prop :=
  ∀ (H : Frame → Id) (app : App) (o : Owner) (r : Request) (a : Behavior),
    (step H app o r a).2.outcome = .rejected → (step H app o r a).1 = o

/-- 7.3.5: the kept request, sent again, gets the kept response again and changes nothing. -/
def RetransmissionIdentical : Prop :=
  ∀ (H : Frame → Id) (app : App) (inputs : List (Request × Behavior)) (k : Exchange) (a : Behavior),
    (run H app {} inputs).kept = some k →
      step H app (run H app {} inputs) k.request a = (run H app {} inputs, k.response)

/-- The frames of a history. -/
def framesOf (xs : List Exchange) : List Frame :=
  xs.flatMap fun x => [.req x.request, .resp x.response]

/-- 7.7.6: if the digest has no collision among the frames of two histories, equal identities of
their last responses imply equal histories. -/
def Commitment : Prop :=
  ∀ (H : Frame → Id) (app : App) (in₁ in₂ : List (Request × Behavior)) (x₁ x₂ : Exchange),
    (history H app in₁).getLast? = some x₁ → (history H app in₂).getLast? = some x₂ →
    (∀ f ∈ framesOf (history H app in₁), ∀ g ∈ framesOf (history H app in₂), H f = H g → f = g) →
    H (.resp x₁.response) = H (.resp x₂.response) → history H app in₁ = history H app in₂

/-- 7.7.4: an `ok` response that the owner sent and that names the identity of a request `r` is the
response of exactly one execution of `r`, if no other request that reached the owner shares `r`'s
identity. The assumption concerns only the frames of the run, so a collision-resistant digest can
meet it; no function from all frames to 256-bit digests is injective. -/
def OkIsOwnExecution : Prop :=
  ∀ (H : Frame → Id) (app : App) (inputs : List (Request × Behavior)) (r : Request) (p : Response),
    p ∈ responsesOf H app {} inputs → p.outcome = .ok → p.request = H (.req r) →
    (∀ q ∈ inputs.map (·.1), H (.req q) = H (.req r) → q = r) →
    ∃ x ∈ history H app inputs, x.request = r ∧ x.response = p ∧
      ∀ y ∈ history H app inputs, y.request = r → y = x
where
  /-- The responses that the owner sends during a sequence of requests. -/
  responsesOf (H : Frame → Id) (app : App) (o : Owner) : List (Request × Behavior) → List Response
    | [] => []
    | (r, a) :: rest => (step H app o r a).2 :: responsesOf H app (step H app o r a).1 rest

/-- 7.5: every rejection except `seq_stale` means that the owner has never executed the request. -/
def RejectionMeansNeverExecuted : Prop :=
  ∀ (H : Frame → Id) (app : App) (inputs : List (Request × Behavior)) (r : Request) (a : Behavior),
    (step H app (run H app {} inputs) r a).2.outcome = .rejected →
    (step H app (run H app {} inputs) r a).2.code ≠ some .seqStale →
    r ∉ (history H app inputs).map (·.request)

/-- 7.5: for every digest, `seq_stale` can answer a request that executed earlier. -/
def StaleMayHaveExecuted : Prop :=
  ∀ H : Frame → Id, ∃ (app : App) (inputs : List (Request × Behavior)) (r : Request) (a : Behavior),
    (step H app (run H app {} inputs) r a).2.code = some .seqStale ∧
    r ∈ (history H app inputs).map (·.request)

/-- The owner executes only requests that it received. -/
def HistoryFromInputs : Prop :=
  ∀ (H : Frame → Id) (app : App) (inputs : List (Request × Behavior)),
    ∀ x ∈ history H app inputs, x.request ∈ inputs.map (·.1)

/-- The calls of a client that follows section 7.6 over a network without faults, after `open`:
each call carries the next sequence number and the identity of the last response it received. -/
def honestCalls (H : Frame → Id) (app : App) (s : Nat) :
    Owner → Nat → Response → List (Nat × Nat × Behavior) → Owner
  | o, _, _, [] => o
  | o, seq, p, (name, body, b) :: rest =>
    let r : Request :=
      { protocol := 2, session := s, seq, op := .call name, ack := some (H (.resp p)), body }
    honestCalls H app s (step H app o r b).1 (seq + 1) (step H app o r b).2 rest

/-- Progress without faults: if the application accepts the `open` body, and every call names an
operation of the contract, has a body that the application finds valid, and returns a result, the
owner executes `open` and then every call with its body, in order. The safety claims above would
also hold for an owner that executes nothing; this claim rules that out. -/
def FaultFreeProgress : Prop :=
  ∀ (H : Frame → Id) (app : App) (s body bound : Nat) (b0 : Behavior)
    (calls : List (Nat × Nat × Behavior)),
    app.opening body = .accept bound →
    (∀ c ∈ calls, app.known c.1 = true ∧ c.2.2.valid = true ∧ ∃ v, c.2.2.result = .result v) →
    let r0 : Request :=
      { protocol := 2, session := s, seq := 0, op := .openSession, ack := none, body }
    (honestCalls H app s (step H app {} r0 b0).1 1 (step H app {} r0 b0).2 calls).log.map
        (fun x => (x.request.op, x.request.body)) =
      (.openSession, body) :: calls.map (fun c => (.call c.1, c.2.1))

end NCP2.Statements
