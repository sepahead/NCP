//! Test-only framed owner for independent Python parity controls.
#[path = "../tests/support/modular_fixture.rs"]
mod fixture;
use ncp_local::modular_owner::{serve, Owner};
use std::cell::Cell;
use std::rc::Rc;

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let mut owner = Owner::new(
        fixture::binding(),
        fixture::Counter::new(Rc::new(Cell::new(0))),
        vec![fixture::SEMANTIC.into()],
    )?;
    serve(
        &mut owner,
        &mut std::io::stdin().lock(),
        &mut std::io::stdout().lock(),
    )?;
    Ok(())
}
