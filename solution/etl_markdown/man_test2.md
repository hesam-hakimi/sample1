Fix the TypeScript type error in etlassistanthandler.ts:

`const changed = applyResult && applyResult.ok && oldText !== newText;`

Root cause: applyResult is typed as unknown/any-object. Do NOT fix by `(applyResult as any)?.ok`.

Preferred fix:
1) Define a shared `ApplyResult` type (ok, filePath, summary, optional reason/details).
2) Ensure `applyResult` is typed at its source:
   - If it comes from `vscode.commands.executeCommand`, use the generic: `executeCommand<ApplyResult>(...)`.
3) Then update the `changed` expression to: `const changed = !!applyResult?.ok && oldText !== newText;`

If typing at source is not possible, add a proper type guard `isApplyResult(v: unknown): v is ApplyResult` and use it to narrow.

Verification:
- run `npm run compile`
- run `npm test`
- confirm extension behavior unchanged
