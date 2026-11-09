# Calculator

A tiny command-line calculator. It adds, subtracts, multiplies and divides two numbers.

## Run it

    python main.py 2 + 3        # prints 5
    python main.py 10 / 4       # prints 2.5
    python main.py 1 / 0        # prints "error: division by zero" and exits with code 1

Write the expression as `<number> <operator> <number>`, with spaces between the three parts.
The operators are `+`, `-`, `*` and `/`.

## Run the tests

    python -m pytest -q

## The config file

`ioc.config.yml` holds the `validate` command. Inception-of-Context runs it after every
change it makes to this project: if the command exits with 0, the change is kept.
