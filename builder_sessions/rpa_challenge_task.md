Build and run the public RPA Challenge form automation.

workflow: workflows/rpa_challenge/main.yaml
target_url: https://rpachallenge.com/
intent: Submit

User instruction: try the automation on https://rpachallenge.com/.
Approval scope: public RPA Challenge fixture data only. Submit each of the 10 challenge rows once. Do not retry submit steps automatically.
Success criteria: final challenge page shows a success-rate message and the run report has all workflow steps passed.
