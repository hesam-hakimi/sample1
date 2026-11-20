Restore one copied file to the reviewed content. In feature/task/TASK_DELIVERY_REGISTER.json, in the reference_control_mapping record "Pilot acceptance/A06", field source_columns, the text "Any new REVIEW_REQUIRED warn/block behavior" has lost two characters: put one backtick character (U+0060) immediately before and one immediately after REVIEW_REQUIRED. Change nothing else in that file and touch no other file.

Then check both:
- SHA-256 of the file, with CRLF converted to LF, is 9cf375d59ad3b2ade7b11a125570194224c9b51a03b67b78f632b3648da30e8b
- py -3 -X utf8 -B feature\validation\validate_workflow_traceability.py exits 0

If either check fails, undo the edit and tell me.
