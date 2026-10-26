---
title: 2026-10-26-legacy-password-login
model: gpt-6.1-sol
effort: high
created: 2026-10-26 18:11:00
last_modified: 2026-10-26 18:11:00
abstract: Separate login credential validation from new password policy so existing accounts can authenticate.
lifecycle: implemented
class: bug-fix
---

# Agent Note: Existing password login

## Problem

An existing account's supplied password can be shorter than the current twelve-character creation policy. The shared registration/login schema and browser input rejected those login requests before checking the stored Argon2 hash, blocking the authorized CMA-263 bot upload.

## Decision

Login accepts nonempty passwords up to 128 characters and verifies them through the existing password, rate-limit, disabled-account and session logic. Registration and password changes retain their minimum of twelve characters. The login form uses the matching bounds and describes entering the existing password; registration keeps the creation-policy hint.

This is an independent authentication fix; the existing C++ competition and fog/terrain decisions are unchanged. No previous note owns this credential-validation decision.

## Alternatives considered

Keeping the shared twelve-character minimum blocks existing credentials before authentication. Resetting the user's password would change the account unnecessarily. Changing registration's minimum would weaken the existing creation policy. Separate login validation addresses the observed failure without either account mutation.

## Consequences

Existing shorter passwords can be authenticated. No password, account data, token or bot source is included in this change. The regression fixture creates a legacy hash only in an isolated temporary database and checks successful/incorrect login, registration and password-change policy, and empty/oversized login rejection.
