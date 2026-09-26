resource "digitalocean_ssh_key" "admin" {
  name       = "story-droplet"
  public_key = var.admin_ssh_public_key
}


resource "digitalocean_droplet" "app" {
  name     = var.droplet_name
  region   = var.region
  size     = var.size
  image    = var.image
  ssh_keys = [digitalocean_ssh_key.admin.id]

  ipv6       = false
  backups    = false
  monitoring = false

  user_data = templatefile("${path.module}/cloud-init.yaml", {
    ssh_public_key = var.admin_ssh_public_key
  })

  # Best-effort guard, not a strict invariant: DigitalOcean doesn't report
  # back which SSH keys or user_data an existing droplet was created with,
  # so declaring either here after import always looks like drift, and
  # ssh_keys is a force-replacement field, so applying that would destroy and
  # recreate this droplet, taking the database (a Docker volume on its own
  # disk, not a separate volume) with it. One consequence: rotating the
  # admin key later won't be picked up by Terraform either; that has to be
  # done by hand (or by deliberately removing ssh_keys from this list).
  #
  # prevent_destroy makes Terraform refuse any plan that would delete this
  # droplet, whether `terraform destroy` or a change that forces replacement
  # (image, region), since that would delete the database too. To replace it
  # deliberately, take a backup first and remove this line for that one run.
  lifecycle {
    prevent_destroy = true
    ignore_changes  = [user_data, ssh_keys]
  }
}


resource "digitalocean_firewall" "app" {
  name        = "story-generator-fw"
  droplet_ids = [digitalocean_droplet.app.id]

  # Open to the world rather than a fixed source: this is a personal
  # deployment reached from a home ISP and CI runners, neither with a stable
  # IP to allowlist. Access is actually gated by key-only auth (root login
  # and password auth are disabled by cloud-init), not by source address.
  inbound_rule {
    protocol         = "tcp"
    port_range       = "22"
    source_addresses = ["0.0.0.0/0"]
  }

  inbound_rule {
    protocol         = "tcp"
    port_range       = "80"
    source_addresses = ["0.0.0.0/0"]
  }

  inbound_rule {
    protocol         = "tcp"
    port_range       = "443"
    source_addresses = ["0.0.0.0/0"]
  }

  # No ::/0 here: the droplet has ipv6 = false, so it has no IPv6 address
  # for an IPv6 source/destination to ever match against.
  outbound_rule {
    protocol              = "tcp"
    port_range            = "all"
    destination_addresses = ["0.0.0.0/0"]
  }

  outbound_rule {
    protocol              = "udp"
    port_range            = "all"
    destination_addresses = ["0.0.0.0/0"]
  }

  outbound_rule {
    protocol              = "icmp"
    destination_addresses = ["0.0.0.0/0"]
  }
}

# CAA: only these CAs may issue certificates for the API's name, so a
# mis-issued certificate from any other CA is refused. Caddy gets its
# certificate from Let's Encrypt and falls back to ZeroSSL (whose CAA name is
# sectigo.com). Set on the API subdomain only: the frontend on the apex is
# served by GitHub Pages, which chooses its own CA.
resource "cloudflare_dns_record" "api_caa" {
  for_each = toset(["letsencrypt.org", "sectigo.com"])

  zone_id = var.cloudflare_zone_id
  name    = var.api_subdomain
  type    = "CAA"
  ttl     = 1
  data = {
    flags = 0
    tag   = "issue"
    value = each.value
  }
}

resource "cloudflare_dns_record" "api" {
  zone_id = var.cloudflare_zone_id
  name    = var.api_subdomain
  type    = "A"
  content = digitalocean_droplet.app.ipv4_address
  ttl     = 1
  proxied = false
}