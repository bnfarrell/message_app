# Task 2 Report: Shift Derivation

## What Was Implemented

Created `server/app/domain/log.py` with:
- `shift_for(prop: Property, at: datetime) -> Shift` function that determines which shift a timestamp falls into on a property's own timezone
- `DEFAULT_SHIFT_BOUNDARIES` constant with default shift boundaries (am: 07:00, pm: 15:00, overnight: 23:00)
- `_boundary()` helper function to resolve custom boundaries from property settings with fallback to defaults

Created `server/tests/test_log_shift.py` with comprehensive test coverage:
- Parametrized test covering 8 local hour cases for default boundaries
- Test for midnight wrapping behavior in property timezone (overnight wraps midnight)
- Test confirming different properties with different timezones produce different labels for the same instant
- Test for custom shift boundaries from property settings
- Test ensuring naive datetimes are rejected

## What Was Tested and Results

### TDD Flow Evidence

**Step 1-2: RED (Test Failure)**
```
cd server && ../.venv/Scripts/python.exe -m pytest tests/test_log_shift.py -q
```

Expected and received:
```
ModuleNotFoundError: No module named 'app.domain.log'
```

The test correctly failed with ImportError as expected before implementation.

**Step 3-4: GREEN (Test Success)**
```
cd server && ../.venv/Scripts/python.exe -m pytest tests/test_log_shift.py -q
```

Result: 12 passed in 0.09s

All tests pass after implementation. Each test verifies specific behavior:
- `test_default_boundaries_partition_the_clock` (8 parametrized cases): Verifies default boundaries correctly partition 24-hour clock
- `test_overnight_wraps_midnight_in_the_property_timezone`: Confirms overnight correctly wraps midnight in property's timezone
- `test_a_different_timezone_gives_a_different_label_for_the_same_instant`: Validates timezone-specific behavior  
- `test_custom_boundaries_from_property_settings`: Confirms custom boundaries override defaults
- `test_a_naive_datetime_is_rejected`: Validates error handling for unaware datetimes

### Full Suite Verification

```
cd server && ../.venv/Scripts/python.exe -m pytest -q
```

Result: 398 passed (baseline: 386 + 12 new tests = 398)

### Linting

```
cd server && ../.venv/Scripts/python.exe -m ruff check .
```

Result: All checks passed!

## Files Changed

- Created: `server/app/domain/log.py` (35 lines)
- Created: `server/tests/test_log_shift.py` (62 lines)

Total: 97 insertions across 2 files

## Self-Review Findings

**Implementation Correctness:**
- Code matches brief specification exactly
- Function signature and behavior correct: `shift_for(prop: Property, at: datetime) -> Shift`
- Handles all three shifts: am, pm, overnight (with overnight wrapping midnight)
- Properly converts UTC datetime to property timezone using ZoneInfo
- Falls back to DEFAULT_SHIFT_BOUNDARIES when property has no custom settings
- Correctly raises ValueError for naive datetimes

**Test Coverage:**
- All 5 test functions implemented as specified
- Parametrized test covers 8 boundary cases
- Tests verify default behavior, timezone handling, custom boundaries, and error handling
- Tests are pure (no DB writes) as specified
- Test helper `_prop()` correctly constructs Property instances for testing

**Code Quality:**
- No extraneous features beyond the brief specification
- Follows existing project patterns (imports, naming conventions)
- Line length complies with 100-character limit
- No dead code or unnecessary abstractions
- Implementation is simple and readable

**No Added Features:**
- Exactly one function created as specified (shift_for)
- No additional helpers except _boundary (necessary for implementation)
- No extra test cases beyond what the brief specified
- File created with only requested content (future tasks will append to this file)

## Concerns

None. The implementation:
- Follows TDD precisely as specified
- Matches the brief code exactly
- Passes all tests
- Passes linting
- Baseline test count increased from 386 to 398 (added 12 tests)
- All 398 tests pass, 0 failed
