output "droplet_ipv4" {
  description = "Public IPv4 address of the Droplet"
  value       = digitalocean_droplet.app.ipv4_address
}

output "api_url" {
  description = "Live API URL"
  value       = "https://${cloudflare_dns_record.api.name}"
}