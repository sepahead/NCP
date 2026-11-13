/-
The claims, without proofs. Review this file: it is what the proofs establish.

`Audit.lean` checks that each proved theorem has exactly the type stated here, and prints the
axioms that it uses. A change to a claim must change this file.
-/
import NCP2.Model
import NCP2.ClientModel

namespace NCP2.Statements

open NCP2

/-- The admitted exchanges after any sequence of inputs to a new owner. -/
def history (H : Frame → Id) (app : App) (inputs : List Input) : List Exchange :=
  (run H app {} inputs).log

/-- The frames of a history. -/
def framesOf (xs : List Exchange) : List Frame :=
  xs.flatMap fun x => [.req x.request, .resp x.response]

/-- 7.7.1: no request is admitted twice. -/
def AtMostOnce : Prop :=
  ∀ (H : Frame → Id) (app : App) (inputs : List Input),
    ((history H app inputs).map (·.request)).Nodup

/-- 7.7.2: the admitted requests carry the sequence numbers 0, 1, 2, ... in order. -/
def InOrder : Prop :=
  ∀ (H : Frame → Id) (app : App) (inputs : List Input),
    (history H app inputs).map (·.request.seq) = List.range (history H app inputs).length

/-- 7.7.3: each admitted request after `open` acknowledges the identity of the response before it. -/
def Acknowledged : Prop :=
  ∀ (H : Frame → Id) (app : App) (inputs : List Input) (i : Nat)
    (h : i + 1 < (history H app inputs).length),
    ((history H app inputs)[i + 1]).request.ack =
      some (H (.resp ((history H app inputs)[i]).response))

/-- 7.3.8: nothing is admitted after an exchange that ends the session. -/
def NothingAfterEnd : Prop :=
  ∀ (H : Frame → Id) (app : App) (inputs : List Input) (i : Nat)
    (h : i + 1 < (history H app inputs).length), ¬ Ends ((history H app inputs)[i])

/-- 7.7.6: a `rejected` response changes no state. -/
def RejectedChangesNothing : Prop :=
  ∀ (H : Frame → Id) (app : App) (o : Owner) (r : Request) (b : Behavior),
    (step H app o r b).2.outcome = .rejected → (step H app o r b).1 = o

/-- 7.3.5: the kept request, sent again, gets the kept response again and changes nothing. -/
def RetransmissionIdentical : Prop :=
  ∀ (H : Frame → Id) (app : App) (inputs : List Input) (k : Exchange) (b : Behavior),
    (run H app {} inputs).kept = some k →
      step H app (run H app {} inputs) k.request b = (run H app {} inputs, k.response)

/-- 7.7.8: if the digest has no collision among the frames of two histories, equal identities of
their last responses imply equal histories. -/
def Commitment : Prop :=
  ∀ (H : Frame → Id) (app : App) (in₁ in₂ : List Input) (x₁ x₂ : Exchange),
    (history H app in₁).getLast? = some x₁ → (history H app in₂).getLast? = some x₂ →
    (∀ f ∈ framesOf (history H app in₁), ∀ g ∈ framesOf (history H app in₂), H f = H g → f = g) →
    H (.resp x₁.response) = H (.resp x₂.response) → history H app in₁ = history H app in₂

/-- 7.7.1, across openings: two runs whose `open` inputs never share a nonce (assumption A4) admit
no common request except `open` itself, if the digest has no collision among the frames of the two
histories. A restarted owner, or an owner that forgot a session, is a new run: a copy of a step
that an earlier opening admitted is never admitted again. -/
def OpeningsDisjoint : Prop :=
  ∀ (H : Frame → Id) (app : App) (in₁ in₂ : List Input),
    (∀ r₁ b₁ r₂ b₂, Input.req r₁ b₁ ∈ in₁ → Input.req r₂ b₂ ∈ in₂ →
      r₁.op = .openSession → r₂.op = .openSession → b₁.nonce ≠ b₂.nonce) →
    (∀ f ∈ framesOf (history H app in₁), ∀ g ∈ framesOf (history H app in₂), H f = H g → f = g) →
    ∀ r ∈ (history H app in₁).map (·.request), r ∈ (history H app in₂).map (·.request) →
      r.seq = 0

/-- 7.7.4: an `ok` response that the owner sent and that names the identity of a request `r` is the
response of exactly one execution of `r`, if no other request among the inputs shares `r`'s
identity. The assumption concerns only the frames of the run, so a collision-resistant digest can
meet it; no function from all frames to 256-bit digests is injective. -/
def OkIsOwnExecution : Prop :=
  ∀ (H : Frame → Id) (app : App) (inputs : List Input) (r : Request) (p : Response),
    p ∈ responses H app {} inputs → p.outcome = .ok → p.request = H (.req r) →
    (∀ q ∈ requests inputs, H (.req q) = H (.req r) → q = r) →
    ∃ x ∈ history H app inputs, x.request = r ∧ x.response = p ∧
      ∀ y ∈ history H app inputs, y.request = r → y = x

/-- 7.7.5: a request that the owner declined never executes, after any further inputs. -/
def DeclinedIsFinal : Prop :=
  ∀ (H : Frame → Id) (app : App) (inputs more : List Input) (r : Request) (p : Response),
    p ∈ responses H app {} inputs → p.outcome = .declined → p.request = H (.req r) →
    (∀ q ∈ requests (inputs ++ more), H (.req q) = H (.req r) → q = r) →
    ∀ x ∈ history H app (inputs ++ more), x.request = r → ¬ Executed x

/-- 7.7.5: a request that got `shutdown` is never admitted, after any further inputs. -/
def ShutdownIsFinal : Prop :=
  ∀ (H : Frame → Id) (app : App) (inputs more : List Input) (r : Request) (p : Response),
    p ∈ responses H app {} inputs → p.code = some .shutdown → p.request = H (.req r) →
    (∀ q ∈ requests (inputs ++ more), H (.req q) = H (.req r) → q = r) →
    r ∉ (history H app (inputs ++ more)).map (·.request)

/-- 7.7.6: every rejection except `seq_stale` means that the owner has not admitted the request. -/
def RejectionMeansNotAdmitted : Prop :=
  ∀ (H : Frame → Id) (app : App) (inputs : List Input) (r : Request) (b : Behavior),
    (step H app (run H app {} inputs) r b).2.outcome = .rejected →
    (step H app (run H app {} inputs) r b).2.code ≠ some .seqStale →
    r ∉ (history H app inputs).map (·.request)

/-- 7.5: for every digest, `seq_stale` can answer a request that executed earlier. -/
def StaleMayHaveExecuted : Prop :=
  ∀ H : Frame → Id, ∃ (app : App) (inputs : List Input) (r : Request) (b : Behavior),
    (step H app (run H app {} inputs) r b).2.code = some .seqStale ∧
    ∃ x ∈ history H app inputs, x.request = r ∧ Executed x

/-- 7.3.10: a stopped owner admits nothing: after a stop, the history does not change. -/
def NothingAfterStop : Prop :=
  ∀ (H : Frame → Id) (app : App) (inputs more : List Input),
    history H app (inputs ++ .stop :: more) = history H app inputs

/-- The owner admits only requests that it received. -/
def HistoryFromInputs : Prop :=
  ∀ (H : Frame → Id) (app : App) (inputs : List Input),
    ∀ x ∈ history H app inputs, x.request ∈ requests inputs

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

/-- 7.7.7: a client that follows section 7.6 has at most one verdict "possibly executed" in a
session, and it is the last. -/
def UnknownIsLast : Prop :=
  ∀ (H : Frame → Id) (s : Nat) (events : List ClientEvent) (i : Nat)
    (h : i + 1 < (clientRun H { session := s } events).verdicts.length),
    ((clientRun H { session := s } events).verdicts[i]).2.1 ≠ .unknown

/-- 7.6.4: a client that follows section 7.6 has the verdict "rejected" only for `open`. The
rejection of any other request ends its session with the verdict "possibly executed": the owner lost
the session, and a delayed copy of `open` opened it again. -/
def RejectedOnlyForOpen : Prop :=
  ∀ (H : Frame → Id) (s : Nat) (events : List ClientEvent),
    ∀ x ∈ (clientRun H { session := s } events).verdicts, x.2.1 = .rejected →
      x.1.op = .openSession

/-- 7.7.7: every verdict "executed" and "not executed" of a client that follows section 7.6 is true
in the owner's history, then and after any further inputs, if every response that the client
accepts is one that the owner sent and no request of the owner's inputs shares the identity of a
request of the client's verdicts unless it is that request. The network between them is arbitrary:
it can lose, repeat, delay, and reorder frames. -/
def ClientTruthful : Prop :=
  ∀ (H : Frame → Id) (app : App) (s : Nat) (events : List ClientEvent) (inputs more : List Input),
    (∀ p ∈ received events, p ∈ responses H app {} inputs) →
    (∀ x ∈ (clientRun H { session := s } events).verdicts,
      ∀ q ∈ requests (inputs ++ more), H (.req q) = H (.req x.1) → q = x.1) →
    ∀ x ∈ (clientRun H { session := s } events).verdicts,
      (x.2.1 = .ran → ∃ y ∈ history H app (inputs ++ more), y.request = x.1 ∧ Executed y ∧
        ∀ z ∈ history H app (inputs ++ more), z.request = x.1 → z = y) ∧
      (x.2.1 = .notRun → ∀ y ∈ history H app (inputs ++ more), y.request = x.1 → ¬ Executed y)

end NCP2.Statements
