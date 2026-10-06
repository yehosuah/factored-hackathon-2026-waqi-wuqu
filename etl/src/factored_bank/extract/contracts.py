"""Reviewed organizer input headers, dictionary v1.0.0 pages 3–12.

Order confirmed against the nine organizer headers inspected during design.
These are structural contracts; all business values remain unchanged text.
"""

CONTRACT_VERSION = "organizer-card-support-v1"
VALIDATION_VERSION = "csv-v1"
ROOT_TABLES = ("customers", "products", "branches", "service_agents")
DAILY_TABLES = (
    "transactions",
    "call_center_interactions",
    "call_transcripts",
    "complaints",
    "satisfaction_surveys",
)
HEADERS = {
    "customers": (
        "customer_id document_number document_type first_name last_name date_of_birth gender "
        "email mobile_phone landline_phone address city state country postal_code detected_accent "
        "segment credit_score estimated_monthly_income occupation marital_status education_level "
        "registration_date registration_branch_id customer_status last_updated accepts_marketing"
    ).split(),
    "products": (
        "product_id customer_id product_type product_number currency current_balance credit_limit "
        "interest_rate opening_date expiration_date opening_branch_id product_status "
        "opening_channel "
        "has_linked_app days_past_due last_transaction_date last_updated"
    ).split(),
    "branches": (
        "branch_id branch_code branch_name branch_type address city state country postal_code "
        "geographic_zone phone email opening_time closing_time has_atms atm_count "
        "has_teller_windows "
        "teller_window_count latitude longitude branch_opening_date branch_status"
    ).split(),
    "service_agents": (
        "agent_id employee_code first_name last_name email phone native_accent country_of_origin "
        "assigned_branch_id agent_type experience_level languages specialty hire_date avg_csat "
        "total_monthly_interactions agent_status work_shift"
    ).split(),
    "transactions": (
        "transaction_id transaction_date process_date product_id customer_id transaction_type "
        "transaction_category amount currency amount_usd channel branch_id merchant_name "
        "merchant_category transaction_country transaction_city transaction_status response_code "
        "is_fraud fraud_score latitude longitude"
    ).split(),
    "call_center_interactions": (
        "interaction_id interaction_date process_date customer_id agent_id interaction_type "
        "channel "
        "contact_reason reason_category duration_seconds wait_time_seconds was_resolved "
        "requires_followup detected_sentiment sentiment_score customer_detected_accent "
        "agent_used_accent was_escalated mentioned_products has_transcript has_recording"
    ).split(),
    "call_transcripts": (
        "transcript_id interaction_id process_date customer_id agent_id full_text customer_text "
        "agent_text detected_language detected_accent accent_confidence detected_keywords "
        "mentioned_entities detected_intents main_topics transcription_model audio_quality "
        "duration_seconds"
    ).split(),
    "complaints": (
        "complaint_id creation_date process_date customer_id case_type category subcategory "
        "reception_channel affected_product_id related_branch_id origin_interaction_id description "
        "claimed_amount currency priority status assigned_agent_id assignment_date "
        "first_response_date "
        "resolution_date closing_date sla_breached resolution_days resolution compensation_granted "
        "resolution_satisfaction is_repeat_complainer"
    ).split(),
    "satisfaction_surveys": (
        "survey_id survey_date process_date interaction_id customer_id agent_id survey_type "
        "send_channel main_score nps_category question_1_text question_1_response question_2_text "
        "question_2_response question_3_text question_3_response open_comments comment_sentiment "
        "response_time_hours campaign_response_rate"
    ).split(),
}
