# Step 6 — Document the feature (README + examples)

## Goal
Make the feature easy to use for your team:
- Explain how to edit configs from Copilot Chat
- List supported file types
- Provide example prompts
- Explain settings (dryRun, autoSave, requireApplyKeyword)

## README sections to add
1. **What it does**
   - “Edit ETL framework HOCON/JSON configs from Copilot Chat”
2. **Prerequisites**
   - Workspace trust
   - Python availability
   - Any required python libs (pyhocon)
3. **How to use**
   - Open ETL config file
   - Ask `@etl_copilot` with explicit “apply”
4. **Examples**
   - “apply: add data_sourcing module reading parquet from SRZ”
   - “apply: change writer path to …”
   - “apply: add transformation step …”
5. **Commands**
   - ETL: Apply Edit to Active File
   - ETL: Validate Active File
   - ETL: Undo Last Edit (if implemented)
6. **Settings**
   - `etlCopilot.edit.dryRun`
   - `etlCopilot.edit.autoSave`
   - `etlCopilot.chat.requireApplyKeyword`

## Verification
1. Follow README steps on a fresh dev host
2. Confirm:
- A user can edit an ETL file from chat
- Validation runs
- Troubleshooting section helps when python fails
