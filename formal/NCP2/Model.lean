/-
The NCP 2 owner as a Lean model (spec/NCP-2.md, sections 6 and 7).

The model follows owner rules 7.3.2 to 7.3.14 for one decoded request. Rule 7.3.1 (bad frames)
belongs to the binding and is outside the model. Identities are digests of frames; the model takes
the digest function `H` as a parameter and compares identities exactly where the rules do.
-/

namespace NCP2

/-- The identity of a frame: its SHA-256 digest (spec 3), kept abstract. -/
abbrev Id := Nat

inductive Op where
  | openSession
  | close
  | call (name : Nat)
  deriving DecidableEq, Repr, Hashable

inductive Outcome where
  | ok
  | rejected
  | ended
  deriving DecidableEq, Repr, Hashable

/-- The codes of section 7.5 that an owner sends in reply to a decoded request. -/
inductive Code where
  | wrongProtocol | notOpen | alreadyOpen | wrongSession | seqStale | seqGap | seqConflict
  | ackMissing | ackMismatch | unknownOp | bodyInvalid | contractMismatch | boundUnacceptable
  | sessionEnded | resultTooLarge | ownerFailure
  deriving DecidableEq, Repr, Hashable

/-- A request (spec 6.1). Bodies are abstract numbers. -/
structure Request where
  protocol : Nat
  session : Nat
  seq : Nat
  op : Op
  ack : Option Id
  body : Nat
  deriving DecidableEq, Repr, Hashable

/-- Response bodies, abstractly. -/
inductive Body where
  | empty
  | detail
  | result (value : Nat)
  | opened (bound : Nat)
  | tooLarge (size bound : Nat)
  deriving DecidableEq, Repr, Hashable

/-- A response to a request (spec 6.2). `request` is the identity of the request it answers. -/
structure Response where
  session : Nat
  seq : Nat
  request : Id
  outcome : Outcome
  code : Option Code
  body : Body
  deriving DecidableEq, Repr, Hashable

inductive Frame where
  | req (r : Request)
  | resp (p : Response)
  deriving DecidableEq, Repr, Hashable

/-- The verdict of section 7.1 on the body of an `open` request. -/
inductive OpenVerdict where
  | accept (bound : Nat)
  | bodyInvalid
  | contractMismatch
  | boundUnacceptable
  deriving DecidableEq, Repr

/-- What the application does when the owner executes a call (rule 7.3.13). -/
inductive AppResult where
  | result (value : Nat)
  | error
  | tooLarge (size : Nat)
  deriving DecidableEq, Repr

/-- What the application does at one step: its verdict on the body of a call (rule 7.3.11) and,
if the owner executes the call, its result (rule 7.3.13). Both are inputs of each step, so the
model covers every behavior of the application, also one that depends on its own state. -/
structure Behavior where
  valid : Bool
  result : AppResult
  deriving DecidableEq, Repr

/-- The parts of the application that stay fixed: the operations of its contract (rule 7.3.11)
and its verdict on the body of an `open` request (section 7.1). -/
structure App where
  known : Nat → Bool
  opening : Nat → OpenVerdict

/-- One exchange that the owner accepted: the request and the response that it sent. -/
structure Exchange where
  request : Request
  response : Response
  deriving DecidableEq, Repr

/-- The owner state of section 7.2. The protocol keeps the identity of the kept request; the
model keeps the request itself, from which the owner uses only its identity. `log` is ghost
state for the proofs: every accepted exchange, `open` first. -/
structure Owner where
  session : Option Nat := none
  bound : Nat := 65536
  high : Nat := 0
  kept : Option Exchange := none
  ended : Bool := false
  log : List Exchange := []
  deriving Repr

/-- An exchange ends the session: a `close`, or a response with outcome `ended` (rule 7.3.14). -/
def Ends (x : Exchange) : Prop := x.request.op = .close ∨ x.response.outcome = .ended

instance (x : Exchange) : Decidable (Ends x) := by unfold Ends; infer_instance

section Step

variable (H : Frame → Id) (app : App)

def reply (r : Request) (outcome : Outcome) (code : Option Code) (body : Body) : Response :=
  { session := r.session, seq := r.seq, request := H (.req r), outcome, code, body }

def reject (r : Request) (code : Code) : Response := reply H r .rejected (some code) .detail

/-- Rule 7.3.13: the response of an accepted request. -/
def execute (bound : Nat) (r : Request) (a : AppResult) : Response :=
  match r.op, a with
  | .call _, .result v => reply H r .ok none (.result v)
  | .call _, .error => reply H r .ended (some .ownerFailure) .empty
  | .call _, .tooLarge size => reply H r .ended (some .resultTooLarge) (.tooLarge size bound)
  | _, _ => reply H r .ok none .empty

/-- Rules 7.3.12 to 7.3.14. -/
def accept (o : Owner) (r : Request) (a : AppResult) : Owner × Response :=
  let p := execute H o.bound r a
  ({ o with high := r.seq, kept := some ⟨r, p⟩, ended := decide (Ends ⟨r, p⟩),
            log := o.log ++ [⟨r, p⟩] }, p)

/-- Section 7.1, for a request that arrives while no session is open. -/
def openStep (o : Owner) (r : Request) : Owner × Response :=
  if r.op = .openSession ∧ r.seq = 0 then
    if r.ack.isSome then (o, reject H r .bodyInvalid) else
    match app.opening r.body with
    | .accept b =>
      let p := reply H r .ok none (.opened b)
      ({ o with session := some r.session, bound := b, high := 0, kept := some ⟨r, p⟩,
                ended := false, log := [⟨r, p⟩] }, p)
    | .bodyInvalid => (o, reject H r .bodyInvalid)
    | .contractMismatch => (o, reject H r .contractMismatch)
    | .boundUnacceptable => (o, reject H r .boundUnacceptable)
  else (o, reject H r .notOpen)

/-- Rules 7.3.6 to 7.3.11, with the identity of the kept response, if any. -/
def checkThenAccept (o : Owner) (keptId : Option Id) (r : Request) (b : Behavior) :
    Owner × Response :=
  if r.seq < o.high then (o, reject H r .seqStale)
  else if r.seq > o.high + 1 then (o, reject H r .seqGap)
  else if o.ended then (o, reject H r .sessionEnded)
  else match r.ack with
    | none => (o, reject H r .ackMissing)
    | some ack =>
      if keptId ≠ some ack then (o, reject H r .ackMismatch)
      else match r.op with
        | .openSession => (o, reject H r .alreadyOpen)
        | .close => accept H o r b.result
        | .call name =>
          if app.known name = false then (o, reject H r .unknownOp)
          else if b.valid = false then (o, reject H r .bodyInvalid)
          else accept H o r b.result

/-- One step of the owner: rules 7.3.2 to 7.3.14 for one decoded request. -/
def step (o : Owner) (r : Request) (b : Behavior) : Owner × Response :=
  if r.protocol ≠ 2 then (o, reject H r .wrongProtocol) else
  match o.session with
  | none => openStep H app o r
  | some s =>
    if r.session ≠ s then (o, reject H r .wrongSession) else
    match o.kept with
    | some k =>
      if r.seq = o.high then
        if H (.req r) = H (.req k.request) then (o, k.response)
        else (o, reject H r .seqConflict)
      else checkThenAccept H app o (some (H (.resp k.response))) r b
    | none => checkThenAccept H app o none r b

/-- The owner after a sequence of requests, each with the application's behavior. -/
def run (o : Owner) : List (Request × Behavior) → Owner
  | [] => o
  | (r, b) :: rest => run (step H app o r b).1 rest

end Step

end NCP2
