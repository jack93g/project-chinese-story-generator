variable "region" {
  description = "DigitalOcean region for the Droplet"
  type        = string
  default     = "fra1"
}

variable "size" {
  description = "DigitalOcean Droplet size"
  type        = string
  default     = "s-1vcpu-2gb"
}

variable "image" {
  description = "Operating system image for the Droplet"
  type        = string
  default     = "ubuntu-24-04-x64"
}

variable "droplet_name" {
  description = "Name of the DigitalOcean Droplet"
  type        = string
  default     = "story-droplet"
}

variable "domain" {
  description = "Domain name for the application"
  type        = string
  default     = "huaben.app"
}

variable "api_subdomain" {
  description = "Subdomain the API is served on, e.g. \"api\" for api.<domain>"
  type        = string
  default     = "api"

  validation {
    condition     = length(trimspace(var.api_subdomain)) > 0
    error_message = "api_subdomain must not be empty (api_url would become \"https://.<domain>\")."
  }
}

variable "admin_ssh_public_key" {
  description = "SSH public key for the administrator"
  type        = string
}

variable "cloudflare_zone_id" {
  description = "Cloudflare zone ID for the domain"
  type        = string
}