//! The clock of the core that runs this program, in GHz (protocol 4 of the NEST campaign).
//!
//! Each iteration makes eight dependent additions on one register. On the cores of Apple silicon
//! an addition takes one cycle and the loop counter runs in parallel, so an iteration takes eight
//! cycles. The runner uses the result to wait until the computer runs at full clock.

#[cfg(target_arch = "aarch64")]
fn main() {
    const ITERATIONS: u64 = 50_000_000;
    let mut value: u64 = 0;
    let started = std::time::Instant::now();
    for _ in 0..ITERATIONS {
        // SAFETY: the instructions only change the one register that they are given.
        unsafe {
            std::arch::asm!(
                "add {v}, {v}, #1", "add {v}, {v}, #1", "add {v}, {v}, #1", "add {v}, {v}, #1",
                "add {v}, {v}, #1", "add {v}, {v}, #1", "add {v}, {v}, #1", "add {v}, {v}, #1",
                v = inout(reg) value,
                options(nomem, nostack),
            );
        }
    }
    let seconds = started.elapsed().as_secs_f64();
    assert_eq!(value, 8 * ITERATIONS);
    println!("{:.3}", (8 * ITERATIONS) as f64 / seconds / 1e9);
}

#[cfg(not(target_arch = "aarch64"))]
fn main() {
    eprintln!("the clock probe needs an aarch64 core");
    std::process::exit(2);
}
