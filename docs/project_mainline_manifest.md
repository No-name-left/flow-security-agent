# Project mainline manifest

## Core workflow files

- `README.md`
- `README_DEPLOY.md`
- `.gitignore`
- `.env.example`
- `requirements.txt`
- `run_stage1.sh`
- `run_stage2.sh`
- `export_submission.sh`
- `configs/competition_label_schema.yaml`
- `configs/llm_qwen35_27b.yaml`
- `scripts/`

No `schemas/` directory is present in the current tree.

## Core RAG files

- `rag/knowledge/competition_labels/`
- `rag/knowledge/signatures/`
- `rag/knowledge/protocols/`
- `rag/knowledge/false_positive_rules/`
- `rag/metadata/rag_manifest.csv`
- `rag/metadata/retrieval_test_queries.jsonl`
- `rag/chunks/rag_chunks.jsonl`
- `rag/index/keyword_index.json`
- `rag/reports/official_code_rag_coverage_audit.*`
- `rag/reports/official_code_rag_rebuild_report.*`
- `rag/reports/official_code_rag_retrieval_test.*`

## Core data metadata

- `datasets/metadata/official_code_data_coverage_audit.*`
- `datasets/metadata/official_code_data_supplement_report.*`
- `datasets/metadata/public_label_mapping_policy.*`
- `datasets/metadata/current_official_code_coverage_matrix.*`
- `datasets/metadata/current_dataset_inventory.*`
- `datasets/metadata/public_dataset_manifest.*`

## Core eval metadata

- `outputs/eval_sets/official_code_balanced_eval_set.*`
- `outputs/eval_sets/small_coverage_test_set.*`
- `docs/official_code_data_rag_sft_small_test_summary.md`

## Core SFT candidate metadata

- `data/sft_candidates/qwen_for_pcap_sft_candidate_manifest.*`
- `data/sft_candidates/sft_candidate_audit_inventory.*`
- `data/sft_candidates/sft_candidate_reviewed_manifest.*`
- `data/sft_candidates/sft_train_val_test_plan.*`
- `docs/sft_candidate_review_report.md`
- `docs/sft_data_readiness_report.md`

## Core Zeek/toolchain reports

- `docs/final_zeek_based_large_scale_test_summary.md`
- `docs/toolchain_status_report.md`
- `outputs/tool_checks/*`
- `outputs/zeek_rebuild/zeek_rebuild_summary.*`
- `outputs/zeek_rebuild/zeek_vs_tshark_fallback_comparison.*`

## Deployment and operation docs

- `README_DEPLOY.md`
- `docs/deployment/bastion_vpn_notes.md`
- `docs/deployment/docker_notes.md`
- `docs/deployment/openeuler_notes.md`
- `docs/deployment/release_package_plan.md`

The requested files `docs/bastion_day1_operation_checklist.md`, `docs/local_openai_compatible_endpoint_notes.md`, and `docs/bastion_minimal_commands.md` are missing in this tree; related deployment notes live under `docs/deployment/`.

## Read these first next time

1. `docs/method_selection_notes.md`
2. `docs/current_project_status_for_assistant.md`
3. `docs/official_code_data_rag_sft_small_test_summary.md`
4. `docs/project_cleanup_summary.md`
5. `docs/project_mainline_manifest.md`
6. `datasets/metadata/official_code_data_coverage_audit.md`
7. `rag/reports/official_code_rag_coverage_audit.md`
8. `docs/sft_candidate_review_report.md`
9. `README.md`
