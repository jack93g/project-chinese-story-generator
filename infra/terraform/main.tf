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

  lifecycle {
    ignore_changes = [user_data, ssh_keys]
  }
}


resource "digitalocean_firewall" "app" {
  name        = "story-generator-fw"
  droplet_ids = [digitalocean_droplet.app.id]

  inbound_rule {
    protocol         = "tcp"
    port_range       = "22"
    source_addresses = ["0.0.0.0/0", "::/0"]
  }

  inbound_rule {
    protocol         = "tcp"
    port_range       = "80"
    source_addresses = ["0.0.0.0/0", "::/0"]
  }

  inbound_rule {
    protocol         = "tcp"
    port_range       = "443"
    source_addresses = ["0.0.0.0/0", "::/0"]
  }

    outbound_rule {
    protocol              = "tcp"
    port_range            = "all"
    destination_addresses = ["0.0.0.0/0", "::/0"]
  }

  outbound_rule {
    protocol              = "udp"
    port_range            = "all"
    destination_addresses = ["0.0.0.0/0", "::/0"]
  }

  outbound_rule {
    protocol              = "icmp"
    destination_addresses = ["0.0.0.0/0", "::/0"]
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