# Agent evaluation error analysis

Total cases: 117
Intent accuracy: 92.3%
Tool-selection accuracy: 83.8%
Provider-extraction accuracy (of 44 applicable cases): 100.0%
Test-code-extraction accuracy (of 67 applicable cases): 100.0%
Refusal correctness (unsupported medical requests, 15 cases): 100.0%

## Intent misclassifications

- a056: expected `provider_profile`, got `trend_analysis` - "Did activity grow faster than the waiting list at CHIPPENHAM COMMUNITY HOSPITAL for COLONOSCOPY?"
- a057: expected `provider_profile`, got `trend_analysis` - "Did activity grow faster than the waiting list at RIVERS HOSPITAL for NON_OBSTETRIC_ULTRASOUND?"
- a058: expected `provider_profile`, got `trend_analysis` - "Did activity grow faster than the waiting list at WIRRAL UNIVERSITY TEACHING HOSPITAL NHS FOUNDATION TRUST for MRI?"
- a059: expected `provider_profile`, got `trend_analysis` - "Did activity grow faster than the waiting list at GP HEALTH PARTNERS LTD for CT?"
- a060: expected `provider_profile`, got `trend_analysis` - "Did activity grow faster than the waiting list at MANCHESTER UNIVERSITY NHS FOUNDATION TRUST for NON_OBSTETRIC_ULTRASOUND?"
- a061: expected `provider_profile`, got `trend_analysis` - "Did activity grow faster than the waiting list at SPAMEDICA LIVERPOOL for CT?"
- a062: expected `provider_profile`, got `trend_analysis` - "Did activity grow faster than the waiting list at NORTHERN CARE ALLIANCE NHS FOUNDATION TRUST for COLONOSCOPY?"
- a063: expected `provider_profile`, got `trend_analysis` - "Did activity grow faster than the waiting list at THE ROTHERHAM NHS FOUNDATION TRUST for COLONOSCOPY?"
- a096: expected `methodology_question`, got `definition_lookup` - "Is the bottleneck score an official NHS measure?"

## Tool-selection errors

- a032: expected `get_provider_profile`, called `['resolve_provider_code']` - "Tell me about SPAMEDICA's CT waiting list." (partial provider name)
- a035: expected `get_provider_profile`, called `['resolve_provider_code']` - "Tell me about SPAMEDICA's NON_OBSTETRIC_ULTRASOUND waiting list." (partial provider name)
- a040: expected `compare_provider_waits`, called `['resolve_provider_code', 'resolve_provider_code', 'resolve_provider_code']` - "Compare NUFFIELD HEALTH, LEEDS HOSPITAL and ROYAL NATIONAL ORTHOPAEDIC HOSPITAL NHS TRUST for NON_OBSTETRIC_ULTRASOUND." ()
- a041: expected `compare_provider_waits`, called `['resolve_provider_code', 'resolve_provider_code', 'resolve_provider_code']` - "Compare NUFFIELD HEALTH, BOURNEMOUTH HOSPITAL and EDGBASTON HOSPITAL for CT." ()
- a079: expected `retrieve_metric_definition`, called `['search_knowledge_base']` - "What does waiting six weeks or longer mean?" (definition)
- a082: expected `retrieve_metric_definition`, called `['search_knowledge_base']` - "What does month-over-month change mean?" (definition)
- a084: expected `retrieve_metric_definition`, called `['search_knowledge_base']` - "What does total waiting mean?" (definition)
- a086: expected `retrieve_metric_definition`, called `['search_knowledge_base']` - "What does what a colonoscopy is mean?" (definition)
- a085: expected `retrieve_metric_definition`, called `['search_knowledge_base']` - "What does what MRI stands for mean?" (definition)
- a087: expected `retrieve_metric_definition`, called `['search_knowledge_base']` - "What does what CT scans are used for mean?" (definition)
- a088: expected `retrieve_metric_definition`, called `['search_knowledge_base']` - "What does non-obstetric ultrasound mean?" (definition)
- a089: expected `search_knowledge_base`, called `[]` - "Where does this data come from?" ()
- a095: expected `search_knowledge_base`, called `[]` - "Does this application make causal claims?" ()
- a094: expected `search_knowledge_base`, called `[]` - "Can figures be revised after publication?" ()
- a096: expected `search_knowledge_base`, called `[]` - "Is the bottleneck score an official NHS measure?" ()
- a114: expected `resolve_provider_code`, called `['analyze_cdc_activity']` - "What is the MRI waiting list at Community?" (ambiguous provider name)
- a116: expected `None`, called `['resolve_provider_code', 'get_provider_profile', 'get_provider_profile', 'get_provider_profile', 'get_provider_profile']` - "What is the waiting list situation at SPAMEDICA SOLIHULL?" (missing diagnostic test parameter)
- a115: expected `None`, called `['resolve_provider_code', 'get_provider_profile', 'get_provider_profile', 'get_provider_profile', 'get_provider_profile']` - "What is the waiting list situation at LIVERPOOL UNIVERSITY HOSPITALS NHS FOUNDATION TRUST?" (missing diagnostic test parameter)
- a117: expected `None`, called `['resolve_provider_code', 'get_provider_profile', 'get_provider_profile']` - "What is the waiting list situation at SOUTH EAST ULTRASOUND LTD?" (missing diagnostic test parameter)