CREATE TABLE automation_audit (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id BIGINT NOT NULL REFERENCES tenants(id),
    user_id BIGINT NOT NULL REFERENCES users(id),
    workflow_id VARCHAR(100) NOT NULL,
    action VARCHAR(20) NOT NULL,
    status VARCHAR(20) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT chk_automation_audit_action
        CHECK (action IN ('activate', 'deactivate')),

    CONSTRAINT chk_automation_audit_status
        CHECK (status IN ('pending', 'success', 'failed'))
);

CREATE INDEX idx_automation_audit_tenant
    ON automation_audit(tenant_id, created_at);
