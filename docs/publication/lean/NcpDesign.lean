/-
NCP system design: machine-checked discrete arithmetic.

This file checks the discrete arithmetic in `docs/publication/ncp-system-design.tex`.
It uses Lean 4 core only. Each section names the equations of the report that it checks.

These theorems prove arithmetic facts about natural numbers and integers. They do not
prove protocol behavior, security, interoperability, physical safety, or controller
stability. The script `scripts/check_ncp_design_lean.sh` runs this file.
-/

namespace NcpDesign

/-! ## Checked addition, equation (1) -/

/-- Checked addition against the largest value `W` of the declared integer type. -/
def cadd (W x y : Nat) : Option Nat :=
  if x + y ≤ W then some (x + y) else none

theorem cadd_defined {W x y : Nat} (h : x + y ≤ W) : cadd W x y = some (x + y) := by
  simp [cadd, h]

theorem cadd_undefined {W x y : Nat} (h : W < x + y) : cadd W x y = none := by
  have : ¬ x + y ≤ W := by omega
  simp [cadd, this]

/-- A defined result is the exact sum and never exceeds `W`, so it never wraps. -/
theorem cadd_exact {W x y z : Nat} (h : cadd W x y = some z) : z = x + y ∧ z ≤ W := by
  unfold cadd at h
  split at h
  · rename_i hle
    injection h with h
    omega
  · contradiction

/-! ## Sequence numbers, equation (2) -/

theorem sequence_bound : (2 ^ 53 - 1 : Nat) = 9007199254740991 := by decide

/-! ## Chunked transfer, equations (4) to (6) -/

/-- The chunk count `m = ⌈ℓ / c⌉`, equation (4). -/
def chunkCount (ℓ c : Nat) : Nat := (ℓ + c - 1) / c

/-- The length of chunk `j`, equation (5). -/
def chunkLen (ℓ c j : Nat) : Nat := min c (ℓ - j * c)

/-- The sum of the first `k` chunk lengths. -/
def tileSum (ℓ c : Nat) : Nat → Nat
  | 0 => 0
  | k + 1 => tileSum ℓ c k + chunkLen ℓ c k

/-- The chunk count satisfies `(m - 1) c < ℓ ≤ m c`. -/
theorem chunkCount_bounds (ℓ c : Nat) (hc : 0 < c) (hℓ : 0 < ℓ) :
    (chunkCount ℓ c - 1) * c < ℓ ∧ ℓ ≤ chunkCount ℓ c * c := by
  unfold chunkCount
  have hdiv := Nat.div_add_mod (ℓ + c - 1) c
  have hmod := Nat.mod_lt (ℓ + c - 1) hc
  rw [Nat.sub_one_mul, Nat.mul_comm ((ℓ + c - 1) / c) c]
  omega

theorem chunkCount_pos (ℓ c : Nat) (hc : 0 < c) (hℓ : 0 < ℓ) : 0 < chunkCount ℓ c := by
  have h := (chunkCount_bounds ℓ c hc hℓ).2
  cases hm : chunkCount ℓ c with
  | zero => rw [hm] at h; omega
  | succ _ => omega

/-- Full chunks before position `k` sum to `k c`. -/
theorem tileSum_full (ℓ c : Nat) : ∀ k, k * c ≤ ℓ → tileSum ℓ c k = k * c := by
  intro k
  induction k with
  | zero => intro _; simp [tileSum]
  | succ k ih =>
    intro h
    rw [Nat.succ_mul] at h
    have hk : k * c ≤ ℓ := by omega
    simp only [tileSum, chunkLen]
    rw [ih hk, Nat.succ_mul]
    omega

/-- The chunks tile the payload with no gap or overlap: their lengths sum to `ℓ`. -/
theorem chunks_tile (ℓ c : Nat) (hc : 0 < c) (hℓ : 0 < ℓ) :
    tileSum ℓ c (chunkCount ℓ c) = ℓ := by
  have hb := chunkCount_bounds ℓ c hc hℓ
  have hpos := chunkCount_pos ℓ c hc hℓ
  obtain ⟨k, hk⟩ : ∃ k, chunkCount ℓ c = k + 1 := ⟨chunkCount ℓ c - 1, by omega⟩
  rw [hk] at hb ⊢
  simp only [Nat.add_sub_cancel] at hb
  simp only [tileSum, chunkLen]
  rw [tileSum_full ℓ c k (by omega)]
  rw [Nat.succ_mul] at hb
  omega

/-- Every chunk has a positive length. -/
theorem chunk_nonempty (ℓ c j : Nat) (hc : 0 < c) (hℓ : 0 < ℓ)
    (hj : j < chunkCount ℓ c) : 0 < chunkLen ℓ c j := by
  have hb := (chunkCount_bounds ℓ c hc hℓ).1
  have hjc : j * c ≤ (chunkCount ℓ c - 1) * c := Nat.mul_le_mul_right c (by omega)
  unfold chunkLen
  omega

/-- Every chunk before the last has the full length `c`. -/
theorem chunk_full_before_last (ℓ c j : Nat) (hc : 0 < c) (hℓ : 0 < ℓ)
    (hj : j + 1 < chunkCount ℓ c) : chunkLen ℓ c j = c := by
  have hb := (chunkCount_bounds ℓ c hc hℓ).1
  have hjc : (j + 1) * c ≤ (chunkCount ℓ c - 1) * c := Nat.mul_le_mul_right c (by omega)
  rw [Nat.succ_mul] at hjc
  unfold chunkLen
  omega

/-- The SDK chunk size gives at most 256 chunks for the largest payload, equation (6). -/
theorem sdk_chunk_bound (ℓ : Nat) (h : ℓ ≤ 8388608) : chunkCount ℓ 32768 ≤ 256 := by
  unfold chunkCount
  omega

theorem sdk_chunk_bound_tight : chunkCount 8388608 32768 = 256 := by decide

/-! ## Logical working extents, equations (7) and (8) -/

theorem owner_extent :
    131072 + 32768 + 16384 + 131072 + 32768 + 14 * 65536 = 1261568 := by decide

theorem client_extent : 131072 + 32768 + 4096 + 14 * 65536 = 1085440 := by decide

theorem sixteen_extents : 16 * 1261568 = 20185088 ∧ 16 * 1085440 = 17367040 := by decide

/-- One full chunk has `4 ⌈32768 / 3⌉` base64 bytes. Two copies fit in two scalar extents. -/
theorem base64_copies :
    4 * ((32768 + 2) / 3) = 43692 ∧ 2 * 43692 = 87384 ∧ 87384 ≤ 2 * 65536 := by decide

/-! ## Sensor clock, equations (9) and (10) -/

/-- The first sample index after body tick `k`: `⌊k f_a / f_b⌋` with 16,000 and 120. -/
def sampleEdge (k : Nat) : Nat := k * 16000 / 120

theorem first_three_ticks :
    sampleEdge 1 - sampleEdge 0 = 133 ∧
    sampleEdge 2 - sampleEdge 1 = 133 ∧
    sampleEdge 3 - sampleEdge 2 = 134 := by decide

theorem sampleEdge_mono (k : Nat) : sampleEdge k ≤ sampleEdge (k + 1) := by
  unfold sampleEdge
  omega

/-- Each group of three ticks holds exactly 400 samples, equation (10). -/
theorem sample_group (u : Nat) :
    (sampleEdge (3 * u + 1) - sampleEdge (3 * u)) +
    (sampleEdge (3 * u + 2) - sampleEdge (3 * u + 1)) +
    (sampleEdge (3 * u + 3) - sampleEdge (3 * u + 2)) = 400 := by
  unfold sampleEdge
  omega

/-- Three ticks at 120 Hz and 400 samples at 16,000 Hz both last 25,000 microseconds. -/
theorem group_duration : 3 * 1000000 = 25000 * 120 ∧ 400 * 1000000 = 25000 * 16000 := by
  decide

/-! ## Spike window, equation (11) -/

/-- For `t_e ≥ Δ_n` and `δ < Δ_n`, the window `(τ_0, τ_1]` is nonempty.
Natural subtraction truncates at zero, which is the `max(0, ·)` of equation (11). -/
theorem spike_window (te Δn δ : Nat) (h1 : Δn ≤ te) (h2 : δ < Δn) :
    (te - δ) - (te - Δn - δ) = min (te - δ) Δn ∧ 0 < (te - δ) - (te - Δn - δ) := by
  omega

/-- The example policy steps NEST once per three body ticks: 24 ticks give 8 steps. -/
theorem engram_steps : 24 = 3 * 8 := by decide

/-! ## Ordered gates, equations (13) to (15) -/

/-- Ordered gate evaluation. The result is the list index of the first false gate.
List index `i` holds gate `i + 1` of the report. -/
def firstFalse : List Bool → Option Nat
  | [] => none
  | true :: gs => (firstFalse gs).map (· + 1)
  | false :: _ => some 0

/-- The receiver admits a frame exactly when every gate is true. -/
theorem firstFalse_none_iff (gs : List Bool) : firstFalse gs = none ↔ ∀ g ∈ gs, g = true := by
  induction gs with
  | nil => simp [firstFalse]
  | cons g gs ih =>
    cases g <;> simp [firstFalse, ih]

/-- The first false gate decides. Every earlier gate is true. -/
theorem firstFalse_decides (gs : List Bool) (j : Nat) (h : firstFalse gs = some j) :
    gs[j]? = some false ∧ ∀ i, i < j → gs[i]? = some true := by
  induction gs generalizing j with
  | nil => simp [firstFalse] at h
  | cons g gs ih =>
    cases g with
    | false =>
      simp [firstFalse] at h
      subst h
      simp
    | true =>
      simp only [firstFalse, Option.map_eq_some_iff] at h
      obtain ⟨j', hj', rfl⟩ := h
      obtain ⟨hfalse, htrue⟩ := ih j' hj'
      refine ⟨by simpa using hfalse, ?_⟩
      intro i hi
      cases i with
      | zero => simp
      | succ i => simpa using htrue i (by omega)

/-! ## Stage times, equations (16) to (19) -/

/-- The sum of the first `k` stage times for contiguous boundaries `b`. -/
def stageSum (b : Nat → Nat) : Nat → Nat
  | 0 => 0
  | k + 1 => stageSum b k + (b (k + 1) - b k)

/-- Contiguous stage boundaries telescope, equation (18). -/
theorem stageSum_telescopes (b : Nat → Nat) (hmono : ∀ i, b i ≤ b (i + 1)) :
    ∀ k, stageSum b k = b k - b 0 ∧ b 0 ≤ b k := by
  intro k
  induction k with
  | zero => simp [stageSum]
  | succ k ih =>
    have hk := hmono k
    simp only [stageSum]
    omega

/-- The sum of `f 0, …, f (k - 1)`. -/
def sumTo (f : Nat → Nat) : Nat → Nat
  | 0 => 0
  | k + 1 => sumTo f k + f k

/-- Termwise ceilings bound the sum, equations (19), (22), and (30). -/
theorem sumTo_le (f g : Nat → Nat) (h : ∀ i, f i ≤ g i) : ∀ k, sumTo f k ≤ sumTo g k := by
  intro k
  induction k with
  | zero => simp [sumTo]
  | succ k ih =>
    have hk := h k
    simp only [sumTo]
    omega

/-! ## Queue admission, equations (27) and (28) -/

/-- Admission keeps the count, bytes, and loss count within bounds. The victim
bounds `e ≤ n` and `R ≤ S` make every natural subtraction exact. -/
theorem queue_admission (n e N S R b Smax g gmax : Nat)
    (he : e ≤ n) (hR : R ≤ S)
    (hn : n - e + 1 ≤ N) (hS : S - R + b ≤ Smax) (hg : g + e ≤ gmax) :
    n - e + 1 ≤ N ∧ S - R + b ≤ Smax ∧ g + e ≤ gmax ∧
    (n - e + 1) + e = n + 1 ∧ (S - R + b) + R = S + b := by
  omega

/-! ## Checked successors, equations (37), (38), (40), and (41) -/

/-- A successor exists below the ceiling, and checked addition cannot fail. -/
theorem successor (hw top W : Nat) (htop : top ≤ W) (h : hw < top) :
    cadd W hw 1 = some (hw + 1) ∧ hw < hw + 1 ∧ hw + 1 ≤ top := by
  refine ⟨cadd_defined (by omega), by omega, by omega⟩

/-- At the ceiling, no successor exists and the epoch seals. -/
theorem exhausted (top : Nat) : ¬ (top < top) := Nat.lt_irrefl top

/-! ## Fixed-layout frames, equations (43) to (45) -/

/-- Bitmap bytes `⌈n_g / 8⌉`, equation (43). -/
def bitmapBytes (ng : Nat) : Nat := (ng + 7) / 8

theorem bitmapBytes_ceil (ng : Nat) :
    ng ≤ bitmapBytes ng * 8 ∧ bitmapBytes ng * 8 < ng + 8 := by
  unfold bitmapBytes
  omega

theorem bitmapBytes_mono {ng Ng : Nat} (h : ng ≤ Ng) : bitmapBytes ng ≤ bitmapBytes Ng := by
  unfold bitmapBytes
  omega

/-- The prepared layout bounds the frame length, equation (45). -/
theorem frame_bound (hdr ng nv w Ng Nv : Nat) (hg : ng ≤ Ng) (hv : nv ≤ Nv) :
    hdr + bitmapBytes ng + nv * w ≤ hdr + bitmapBytes Ng + Nv * w := by
  have h1 := bitmapBytes_mono hg
  have h2 : nv * w ≤ Nv * w := Nat.mul_le_mul_right w hv
  omega

/-- Fleet groups: group `g` owns command values `3g`, `3g + 1`, and `3g + 2`.
These groups partition the `3N` command values. -/
theorem fleet_groups (N i : Nat) (hi : i < 3 * N) :
    i / 3 < N ∧ 3 * (i / 3) ≤ i ∧ i ≤ 3 * (i / 3) + 2 := by
  omega

theorem fleet_bitmap_states : 2 ^ 1 = 2 ∧ 2 ^ 2 = 4 ∧ 2 ^ 3 = 8 ∧ bitmapBytes 3 = 1 := by
  decide

/-! ## Freshness grant, equations (52) to (54) -/

/-- A grant is live at tick `t` exactly when `t_iss ≤ t < d`. The exclusive
deadline rejects the tick `d` itself. -/
def live (tiss d t : Nat) : Bool := decide (tiss ≤ t ∧ t < d)

theorem deadline_exclusive (tiss Δ : Nat) : live tiss (tiss + Δ) (tiss + Δ) = false := by
  simp [live]

/-! ## Scalar sampled loop, equation (58) -/

/-- With `Δ = x / s` seconds for a positive scale `s`, the scaled factor is
`s Φ = s - 2x`. The loop is stable exactly when `|s - 2x| < s`, which holds exactly
when `0 < Δ < 1` second. The equivalence holds for every integer `s`. -/
theorem scalar_stability (s x : Int) :
    (-s < s - 2 * x ∧ s - 2 * x < s) ↔ (0 < x ∧ x < s) := by
  omega

/-- At `Δ = 0.1` second, `Φ = 0.8`. At `Δ = 1` second, `Φ = -1`. -/
theorem scalar_examples : (10 - 2 * 1 : Int) = 8 ∧ (10 - 2 * 10 : Int) = -10 := by decide

/-! ## Silence deadline and horizon bound, Sections 18 and 20 -/

/-- The sustained-silence deadline in milliseconds for a timeout `T` in milliseconds. -/
def silenceDeadline (T : Nat) : Nat := min (20 * min T 60000) 60000

theorem silence_examples : silenceDeadline 500 = 10000 := by decide

theorem silence_saturates (T : Nat) (h : 3000 ≤ T) : silenceDeadline T = 60000 := by
  unfold silenceDeadline
  omega

/-- For an effective lifetime `a` and a step `dt`, both positive milliseconds, the
count `N = ⌈a / dt⌉ - 1` is the largest step count with every step strictly before
the inclusive expiry `a`. -/
theorem horizon_steps (a dt : Nat) (ha : 0 < a) (hdt : 0 < dt) :
    ((a + dt - 1) / dt - 1) * dt < a ∧ a ≤ ((a + dt - 1) / dt - 1 + 1) * dt := by
  have hb := chunkCount_bounds a dt hdt ha
  unfold chunkCount at hb
  have hpos : 0 < (a + dt - 1) / dt := chunkCount_pos a dt hdt ha
  rw [Nat.sub_add_cancel hpos]
  exact hb

/-! ## Reported campaign consistency, Section 5.2 and Table 5 -/

/-- The sensor transfer counted 3,200 pressure samples in 24 body ticks. -/
theorem m1_samples : sampleEdge 24 = 3200 := by decide

/-- The city maximum batch recorded the intervals `[0,133)`, `[133,266)`, and `[266,400)`. -/
theorem city_intervals :
    sampleEdge 1 = 133 ∧ sampleEdge 2 = 266 ∧ sampleEdge 3 = 400 := by decide

/-- Ticks 1 and 2 retained 27,857,056 bytes each and tick 3 retained 27,857,088 bytes.
The 32-byte difference is one more 8-byte sample for each of four microphones. -/
theorem city_batch :
    2 * 27857056 + 27857088 = 83571200 ∧ 27857088 - 27857056 = 4 * 8 := by decide

/-- The required 7,200-tick horizon spans 60 seconds and 960,000 pressure samples. -/
theorem city_horizon : sampleEdge 7200 = 960000 ∧ 7200 = 60 * 120 := by decide

end NcpDesign
