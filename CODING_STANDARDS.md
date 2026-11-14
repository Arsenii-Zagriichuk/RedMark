# Coding standards

The judgement calls `code-review` checks on the Standards axis. Anything a check can catch belongs in CI or a test instead, not here. From the review standards in the [team plan](docs/team-plan.md#the-ticket-cycle-matt-pococks-skills).

- **Expected values are independent.** A test's expected value comes from a worked example or a known answer, never from recomputing it the way the code does.
- **Every number traces to a script.** A number on screen or in a results file can be traced to the script that wrote it.
- **Simulated is always labelled.** The "simulated" label is visible wherever a simulated result is shown: in the app, on slides and in videos.
- **Overlays prove the claim.** An overlay image actually shows what the pull request claims (alignment, match outline, route).
- **Only the ticket.** Nothing beyond the ticket: no extra options, layers or settings that no ticket asked for.
