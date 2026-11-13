/-
The verified owner model as a test oracle (see README.md).

The conformance harness `../model/conformance.py --oracle` sends one input per line and compares the
real owners' outcomes and codes with the ones printed here. The step function is `NCP2.step`, the
function that `NCP2.Owner` and `NCP2.Client` prove safe.

Input, one per line:
  reset     a new owner, for a new trace
  restart   a new owner in the same trace: the identities printed so far stay valid
  stop
  req SEQ OP ACK BAD FAIL BIG SESSION PROTOCOL NONCE OPEN
    OP        open | close | ping | step | unknown
    ACK       - | an identity printed earlier by this oracle
    BAD       1 if the application must find the body invalid, else 0
    FAIL      1 if the application must raise when it executes the request, else 0
    BIG       1 if the result must be too large for the session, else 0
    SESSION   1 for the harness's session, 2 for another one
    PROTOCOL  2, or another number
    NONCE     the nonce of an opening that this request makes
    OPEN      the application's verdict on an open body: accept | body_invalid |
              contract_mismatch | bound_unacceptable | refused
Output, one line per input: OUTCOME CODE IDENTITY (CODE and IDENTITY are - when absent), or - for
reset, restart, and stop.

Identities are hashes of the abstract frames; the oracle stops with an error if two different
frames ever share one, so every run it completes is a run of the model under an injective digest.
-/
import NCP2

open NCP2

def codeName : Code → String
  | .wrongProtocol => "wrong_protocol" | .notOpen => "not_open" | .alreadyOpen => "already_open"
  | .wrongSession => "wrong_session" | .seqStale => "seq_stale" | .seqGap => "seq_gap"
  | .seqConflict => "seq_conflict" | .ackMissing => "ack_missing" | .ackMismatch => "ack_mismatch"
  | .unknownOp => "unknown_op" | .bodyInvalid => "body_invalid"
  | .contractMismatch => "contract_mismatch" | .boundUnacceptable => "bound_unacceptable"
  | .refused => "refused" | .sessionEnded => "session_ended" | .resultTooLarge => "result_too_large"
  | .ownerFailure => "owner_failure" | .sessionExpired => "session_expired" | .shutdown => "shutdown"

def outcomeName : Outcome → String
  | .ok => "ok" | .declined => "declined" | .rejected => "rejected" | .ended => "ended"

def digest (f : Frame) : Id := (hash f).toNat

/-- The harness's application: one operation, `step` (name 0). The body of an `open` request
encodes the application's verdict on it. -/
def harnessApp : App where
  known name := name == 0
  opening body := match body with
    | 0 => .accept 65536
    | 1 => .bodyInvalid
    | 2 => .contractMismatch
    | 3 => .boundUnacceptable
    | _ => .refused

def openCode : String → Option Nat
  | "accept" => some 0 | "body_invalid" => some 1 | "contract_mismatch" => some 2
  | "bound_unacceptable" => some 3 | "refused" => some 4 | _ => none

/-- The body records the BAD, FAIL, and BIG flags, so that requests that differ in them are
different frames with different identities, as in the harness. -/
def parseLine (line : String) : Option Input := do
  let parts := (line.splitOn " ").filter (· ≠ "")
  match parts with
  | ["stop"] => some .stop
  | ["req", seqS, opS, ackS, badS, failS, bigS, sessionS, protocolS, nonceS, openS] =>
    let seq ← seqS.toNat?
    let op ← match opS with
      | "open" => some Op.openSession | "close" => some Op.close | "ping" => some Op.ping
      | "step" => some (Op.call 0) | "unknown" => some (Op.call 1) | _ => none
    let ack ← if ackS == "-" then some none else (some ∘ some) <$> ackS.toNat? |>.join
    let session ← sessionS.toNat?
    let protocol ← protocolS.toNat?
    let nonce ← nonceS.toNat?
    let verdict ← openCode openS
    let bad := badS == "1"
    let fail := failS == "1"
    let big := bigS == "1"
    let body := if op = .openSession then verdict
      else (if bad then 2 else 0) + (if fail then 1 else 0) + (if big then 4 else 0)
    let request : Request := { protocol, session, seq, op, ack, body }
    let result := if fail then AppResult.error else if big then .tooLarge 0 else .result seq
    some (.req request { valid := !bad, result, nonce })
  | _ => none

partial def loop (stdin : IO.FS.Stream) (stdout : IO.FS.Stream) (o : Owner)
    (seen : List (Id × Frame)) : IO Unit := do
  let line ← stdin.getLine
  if line.isEmpty then return
  let line := line.trimAsciiEnd.toString
  if line.isEmpty then loop stdin stdout o seen else
  if line == "reset" || line == "restart" then
    stdout.putStrLn "-"
    stdout.flush
    loop stdin stdout {} (if line == "reset" then [] else seen)
  else
  let some input := parseLine line
    | throw (IO.userError s!"cannot parse: {line}")
  match input with
  | .stop =>
    stdout.putStrLn "-"
    stdout.flush
    loop stdin stdout (apply digest harnessApp o .stop) seen
  | .req r b =>
    let (o', p) := step digest harnessApp o r b
    -- Check that the digest is injective on every frame seen so far.
    let mut seen := seen
    for f in [Frame.req r, Frame.resp p] do
      match seen.find? (·.1 == digest f) with
      | some (_, g) => if g != f then throw (IO.userError "digest collision")
      | none => seen := (digest f, f) :: seen
    let ident := if p.outcome == .rejected then "-" else toString (digest (.resp p))
    let code := match p.code with | some c => codeName c | none => "-"
    stdout.putStrLn s!"{outcomeName p.outcome} {code} {ident}"
    stdout.flush
    loop stdin stdout o' seen

def main : IO Unit := do
  loop (← IO.getStdin) (← IO.getStdout) {} []
