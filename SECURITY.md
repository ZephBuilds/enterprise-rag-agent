# Security policy

## Scope

This repository is a fictional, offline portfolio demonstration. It contains
no production documents, credentials, customer data, network clients, vector
database, or model API integration.

## Trust model

- Evaluation specifications are validated before execution.
- Evaluation files select only allowlisted fixture identifiers and cannot
  provide filesystem paths.
- Non-current sources are excluded before ranking.
- Authoritative sources outrank lower-authority conflicting text.
- Invalid evaluations fail closed with a sanitized public error.
- The container runs as an unprivileged numeric user with networking disabled
  by the documented verification command.

## Reporting

Do not open a public issue containing a secret or private document. This public
demo should never require either. Report a suspected vulnerability privately
to the repository owner after publication.
