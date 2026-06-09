variable "project_id" {
  type = string
}

variable "region" {
  type    = string
  default = "australia-southeast1"
}

variable "service_name" {
  type    = string
  default = "wildfire-ops-backend"
}

variable "artifact_repository_id" {
  type    = string
  default = "wildfire-ops"
}

variable "image_uri" {
  type = string
}

variable "adk_gemini_model" {
  type    = string
  default = "gemini-2.5-flash"
}

variable "cors_origins" {
  type = list(string)
  default = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:3001",
    "http://127.0.0.1:3001",
  ]
}

variable "create_elastic_secret_placeholders" {
  type    = bool
  default = false
}

variable "elastic_evidence_provider" {
  type    = string
  default = "real"
}

variable "elastic_mcp_tool_name" {
  type    = string
  default = "search_wildfire_ops_knowledge"
}

variable "elastic_kibana_url_secret_id" {
  type    = string
  default = "elastic-kibana-url"
}

variable "elastic_api_key_secret_id" {
  type    = string
  default = "elastic-api-key"
}
