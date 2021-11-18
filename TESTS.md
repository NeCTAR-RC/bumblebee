# Bumblebee Testing

The long term goal is to have a complete set of unit, integration and UI tests
for the entire codebase.  We also run pep8 tests over the codebase to pick up
python style, etc issues.

We are not there yet.

## Unit and request tests

There is a `tests/` directory for each of the Django apps;
`researcher_workspace/tests`, `researcher_desktop/tests`,
`vm_manager/tests` and `guacamole/tests`.

We use Python's `unittest` and `unittest.mock`, together with `factoryboy`.
The directory structure pattern in each `tests` directory is something
like this:

```
  tests:
    factories.py         # factoryboy factory classes
    fakes.py             # (optional) more complex fake classes, based on mocks
    test_requests.py     # tests using the Django test client
    ...                  
    unit:                # classic mock-based unit tests
      test_views.py      # unit tests for view methods
      test_models.py     # unit tests for model / model manager classes
      ...
```

If the `test_*.py` files get unmanagebly large, they can be split; e.g.
into modules in the `unit` tree.  Other "kinds" of test can be added to
the pattern as required.

## Selenium tests

We intend to use selenium to implement UI tests and tests of the various
Desktop launch, boost, shelve, etc life-cyles.

No selenium tests are implemented yet.

## Test configs and settings

The tox configs are in the top directory.  There is a separate settings.py
file that provides the Django configs for the various test cases run via tox.

## Running tests

Currently ...

```
tox -e py38              # run standard tests
tox -e pep8              # run style checks
```
