output "droplet_ipv4" {
  description = "Public IPv4 address of the Droplet"
  value       = digitalocean_droplet.app.ipv4_address
}

output "api_url" {
  description = "Live API URL"
  # Built from the input variables rather than cloudflare_dns_record.api.name,
  # so the output doesn't depend on how the provider reports that attribute.
  value = "https://${var.api_subdomain}.${var.domain}"
}