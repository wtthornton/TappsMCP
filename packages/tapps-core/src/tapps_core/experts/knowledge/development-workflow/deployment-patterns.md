# Deployment Patterns

## Overview

Deployment patterns define how applications are released to production environments. Choosing the right pattern minimizes downtime, reduces risk, and enables rapid rollback.

## Deployment Strategies

### Rolling Deployment
- Gradual replacement of instances
- Zero downtime when done correctly
- Supports rollback
- Uses load balancing

**Process:**
1. Deploy to subset of instances
2. Health check new instances
3. Gradually shift traffic
4. Complete when all instances updated

### Blue-Green Deployment
- Two identical production environments
- Instant traffic switch
- Zero downtime
- Easy rollback

**Process:**
1. Deploy new version to "green" environment
2. Run smoke tests
3. Switch traffic from "blue" to "green"
4. Keep "blue" for rollback if needed

### Canary Deployment
- Gradual rollout to subset of users
- Monitor metrics closely
- Expand if successful
- Rollback if issues detected

**Process:**
1. Deploy to small percentage (5-10%)
2. Monitor metrics (errors, latency, etc.)
3. Gradually increase percentage
4. Complete rollout or rollback as needed

### Feature Flags
- Toggle features without deployment
- A/B testing capability
- Gradual feature rollout
- Instant rollback

**Use Cases:**
- New features
- Experimental functionality
- Regional rollouts
- User segmentation

## Deployment Automation

### Infrastructure as Code
```yaml
# Terraform example
resource "aws_ecs_service" "app" {
  name            = "my-app"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.app.arn
  desired_count   = 3
  
  deployment_configuration {
    maximum_percent         = 200
    minimum_healthy_percent = 100
  }
}
```

### Deployment Pipelines
- Automated testing
- Build artifacts
- Deploy to staging
- Run integration tests
- Deploy to production
- Health checks
- Monitoring

## Deployment Best Practices

### Pre-Deployment
- ✅ All tests passing
- ✅ Code review approved
- ✅ Database migrations tested
- ✅ Rollback plan ready
- ✅ Monitoring in place
- ✅ Team notified

### During Deployment
- Deploy during low-traffic periods
- Monitor metrics closely
- Have rollback ready
- Communicate status
- Document deployment

### Post-Deployment
- Verify health checks
- Monitor for errors
- Check key metrics
- Gather feedback
- Document issues

## Rollback Strategies

### Immediate Rollback
- Keep previous version ready
- Quick traffic switch
- Minimize impact
- Automated triggers

### Gradual Rollback
- Reduce new version percentage
- Increase old version percentage
- Monitor recovery
- Complete rollback if needed

### Database Rollbacks
- Version-controlled migrations
- Forward and backward migrations
- Test rollback procedures
- Backup before migrations

## Zero-Downtime Deployment

### Requirements
- Load balancing
- Multiple instances
- Health checks
- Traffic routing
- Session persistence (if needed)

### Process
1. Deploy new version to new instances
2. Health check new instances
3. Gradually shift traffic
4. Monitor metrics
5. Drain old instances when complete

## Deployment Environments

### Development
- Local development
- Fast iteration
- Relaxed requirements
- Developer control

### Staging
- Production-like environment
- Integration testing
- Performance testing
- User acceptance testing

### Production
- Live user traffic
- Highest reliability
- Full monitoring
- Change controls

## Monitoring and Alerting

### Key Metrics
- **Error Rate**: Percentage of failed requests
- **Latency**: Response time percentiles
- **Throughput**: Requests per second
- **Resource Usage**: CPU, memory, disk
- **Business Metrics**: Conversion, revenue

### Alerting
- **Critical**: Immediate response needed
- **Warning**: Investigate soon
- **Info**: Monitor and log

## Deployment Tools

### Container Orchestration
- **Kubernetes**: Container orchestration
- **Docker Swarm**: Container clustering
- **ECS**: AWS container service
- **Nomad**: Workload orchestration

### Deployment Platforms
- **Heroku**: Platform as a service
- **AWS Elastic Beanstalk**: Application hosting
- **Google App Engine**: Managed platform
- **Azure App Service**: Web app hosting

### CI/CD Tools
- **Jenkins**: Automation server
- **GitLab CI**: Built-in CI/CD
- **GitHub Actions**: GitHub-integrated
- **CircleCI**: Cloud CI/CD

## MCP Server Distribution Channels

MCP servers have unique distribution needs: they must be discoverable by AI clients,
configurable without manual JSON editing, and runnable without installing language
runtimes. The following channels address these needs:

### Docker MCP Toolkit (Recommended for End Users)

The Docker MCP Toolkit provides zero-dependency distribution via Docker Desktop:

- **MCP Catalog**: 300+ verified server images, browsable in Docker Desktop UI
- **MCP Gateway**: stdio proxy managing container lifecycle -- one config entry per profile
- **Profiles**: Named server collections (e.g., "tapps-platform" bundles tapps-mcp + docs-mcp)
- **Dynamic MCP**: Agents discover and add servers mid-conversation

Client configuration (single gateway entry):

```json
{
  "mcpServers": {
    "tapps-platform": {
      "command": "docker",
      "args": ["mcp", "gateway", "run", "--profile", "tapps-platform"]
    }
  }
}
```

Publish to catalog via PR to `docker/mcp-registry`. Images are signed with SBOM.

### PyPI (Standard Python)

```bash
pip install tapps-mcp
# or
uv add tapps-mcp
```

Requires Python 3.12+. Best for developers already in a Python environment.

### PyInstaller Executables

Pre-built `.exe` files for Windows. No Python needed. Best for air-gapped or
offline environments. Rebuilt manually per release.

### Profile-Based vs Single-Server Deployment

| Approach | Config Entries | Use Case | Maintenance |
|----------|---------------|----------|-------------|
| **Profile-based** (gateway) | 1 entry per profile | Teams, multi-server setups | Update profile, all clients inherit |
| **Single-server** (direct) | 1 entry per server | Solo dev, minimal setup | Update each client config separately |

Profile-based deployment is recommended when using two or more MCP servers.
The gateway manages container lifecycle, routing, and secrets centrally.
Single-server deployment is simpler for one-off use but does not scale well
when adding companions like Context7 or GitHub MCP.

### Transport Selection

| Channel | Transport | Multi-Client | Auto-Update |
|---------|-----------|-------------|-------------|
| Docker MCP | stdio (via gateway) | Yes (via gateway) | Yes (image tags) |
| PyPI | stdio (direct) | No | Manual pip upgrade |
| Exe | stdio (direct) | No | Manual rebuild |

## Anti-Patterns

1. **Big Bang Deployments**: Deploy everything at once
2. **Manual Deployments**: Use automation
3. **No Rollback Plan**: Always have rollback
4. **Skipping Tests**: Test before deploying
5. **Ignoring Monitoring**: Monitor during deployment
6. **No Health Checks**: Verify deployment success
