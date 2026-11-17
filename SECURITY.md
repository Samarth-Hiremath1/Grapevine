# Security policy

## Supported versions

Only the latest release receives fixes. Before the first release, that is the
`main` branch.

## Reporting a vulnerability

Please do not open a public issue. Use GitHub's private vulnerability
reporting: the **Security** tab of this repository, then **Report a
vulnerability**. You should get an acknowledgement within a week.

## Scope

Grapevine runs offline by default. The parts that touch the outside world are
the provider clients in `grapevine/rollout/client.py`, which read API keys from
the environment or a local `.env` file, and the eval runners that call them.
Reports about key handling, about a run writing a key or a prompt somewhere it
should not, or about the audit being made to pass a flawed environment on
purpose are all in scope.
