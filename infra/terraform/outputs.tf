output "droplet_ipv4" {
  description = "Public IPv4 address of the Droplet"
  value       = digitalocean_droplet.app.ipv4_address
}

output "api_url" {
  description = "Live API URL"
  # Built from the input variables rather than cloudflare_dns_record.api.name:
  # that attribute is provider-computed, and in practice already returns the
  # full FQDN even though "name" is configured as just the subdomain (a
  # v5-provider quirk we don't want this output silently depending on).
  value = "https://${var.api_subdomain}.${var.domain}"
}