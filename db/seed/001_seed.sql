-- Cocopan IMS — baseline reference seed
-- Source: docs/SPEC.md §7.1 (roles), §7.3 (permission matrix), §4.8/§4.3 examples
--
-- Deliberately does NOT seed: item/item_category, location/branches, calendar
-- dates, or business-specific reason codes beyond CORRECTION. Those are real
-- client data (§16 open items #6, #8, #12) or admin-owned reference data
-- (§5.7 rule 1: every reference table gets a CRUD UI) — inventing plausible-
-- looking branches or SKUs here would be indistinguishable from real data
-- later. Only structural, spec-mandated seed values are included.

BEGIN;

-- =====================================================================
-- §7.1 Roles — mapped 1:1 to real Cocopan positions
-- =====================================================================
INSERT INTO core.role (role_code, label, description, is_system) VALUES
    ('SYS_ADMIN',             'System Administrator',      'IT / systems. Configuration, users, integrations.', TRUE),
    ('DEMAND_PLANNER',        'Demand Planner',             'Demand planning analyst. Owns order runs, forecast and parameters.', TRUE),
    ('CX_SPECIALIST',         'CX Specialist',               'Customer Experience team. Reviews and recommends order adjustments.', TRUE),
    ('OPS_MANAGER',           'Operations Manager',          'Owns a group of branches. Final order adjustment for own branches.', TRUE),
    ('AREA_HEAD',             'Area / Regional Head',        'Oversight across several Operations Managers.', TRUE),
    ('STORE_HEAD',            'Store Head',                  'Counts, receiving, waste, branch review.', TRUE),
    ('STORE_TEAM',            'Store Team Member',           'Count and waste capture only.', TRUE),
    ('PPIC_PLANNER',          'PPIC Planner',                'Receives and confirms production requirement.', TRUE),
    ('COMMISSARY_SUPERVISOR', 'Commissary Production Supervisor', 'Production receipts, dispatch confirmation.', TRUE),
    ('FINANCE_ANALYST',       'Finance Analyst',             'Cost, waste valuation, analytics. Read-only.', TRUE),
    ('EXECUTIVE',             'Executive',                   'CFO / leadership. Dashboards and scorecards. Read-only.', TRUE),
    ('INTEGRATION',           'Integration Service Account', 'API ingestion only.', TRUE);

-- =====================================================================
-- §7.3 Permissions (abridged matrix as given; is_destructive set for
-- delete/lock/submit-type actions per §7.4)
-- =====================================================================
INSERT INTO core.permission (permission_code, resource, action, label, is_destructive) VALUES
    ('item.read',                 'item',        'read',                 'View items', FALSE),
    ('item.create',               'item',        'create',               'Create items', FALSE),
    ('item.update',               'item',        'update',               'Update items', FALSE),
    ('item.delete',                'item',        'delete',               'Delist an item', TRUE),
    ('item.price.update',          'item',        'price_update',         'Update item price/cost', FALSE),
    ('location.read',              'location',    'read',                 'View branches', FALSE),
    ('location.create',            'location',    'create',               'Create branches', FALSE),
    ('location.update',            'location',    'update',               'Update branches', FALSE),
    ('location.status_change',     'location',    'status_change',        'Change branch lifecycle status', TRUE),
    ('location.assign_om',         'location',    'assign_om',            'Assign Operations Manager', FALSE),
    ('location.closure.manage',    'location',    'closure_manage',       'Manage branch closures', FALSE),
    ('assortment.manage',          'assortment',  'manage',               'Manage assortment templates/branch assortment', FALSE),
    ('refdata.manage',             'refdata',     'manage',               'Manage reference data (categories, clusters, areas, routes, calendar)', FALSE),
    ('param.read',                 'param',       'read',                 'View parameter sets', FALSE),
    ('param.update',               'param',       'update',               'Update parameter sets', FALSE),
    ('order.read',                 'order',       'read',                 'View orders', FALSE),
    ('order.generate',             'order',       'generate',             'Generate an order run', FALSE),
    ('order.adjust_cx',            'order',       'adjust_cx',            'Enter CX recommendation', FALSE),
    ('order.adjust_om',            'order',       'adjust_om',            'Enter OM adjustment', FALSE),
    ('order.lock',                 'order',       'lock',                 'Lock an order run', TRUE),
    ('order.submit_ppic',          'order',       'submit_ppic',          'Submit order to PPIC', TRUE),
    ('order.confirm_production',   'order',       'confirm_production',   'Confirm production requirement', FALSE),
    ('count.submit',               'count',       'submit',               'Submit a physical count', FALSE),
    ('count.approve',              'count',       'approve',              'Approve a count variance', FALSE),
    ('receiving.confirm',          'receiving',   'confirm',              'Confirm delivery receipt', FALSE),
    ('waste.record',               'waste',       'record',               'Record waste', FALSE),
    ('movement.adjust',            'movement',    'adjust',               'Manual stock adjustment', TRUE),
    ('accuracy.read',              'accuracy',    'read',                 'View accuracy dashboards', FALSE),
    ('user.manage',                'user',        'manage',               'Manage users', TRUE),
    ('role.manage',                'role',        'manage',               'Manage roles and permissions', TRUE),
    ('audit.read',                 'audit',       'read',                 'View audit log', FALSE),
    ('integration.manage',         'integration', 'manage',               'Manage integration sources, mapping profiles, webhooks', FALSE),
    ('export.data',                'export',      'data',                 'Export data', FALSE);

-- =====================================================================
-- §7.3 Role -> permission grants (the ✓ marks in the matrix), plus the
-- EXECUTIVE and COMMISSARY_SUPERVISOR grants defined in prose beneath it.
-- INTEGRATION is a service-account role; scope is configured per key
-- (core.api_key.scopes), not via role_permission, so it gets no grants here.
-- =====================================================================
INSERT INTO core.role_permission (role_code, permission_code)
SELECT r.role_code, p.permission_code
FROM (VALUES
    -- item
    ('SYS_ADMIN','item.read'), ('DEMAND_PLANNER','item.read'), ('CX_SPECIALIST','item.read'),
    ('OPS_MANAGER','item.read'), ('AREA_HEAD','item.read'), ('STORE_HEAD','item.read'),
    ('STORE_TEAM','item.read'), ('PPIC_PLANNER','item.read'), ('FINANCE_ANALYST','item.read'),
    ('SYS_ADMIN','item.create'), ('DEMAND_PLANNER','item.create'),
    ('SYS_ADMIN','item.update'), ('DEMAND_PLANNER','item.update'),
    ('SYS_ADMIN','item.delete'),
    ('SYS_ADMIN','item.price.update'), ('FINANCE_ANALYST','item.price.update'),
    -- location
    ('SYS_ADMIN','location.read'), ('DEMAND_PLANNER','location.read'), ('CX_SPECIALIST','location.read'),
    ('OPS_MANAGER','location.read'), ('AREA_HEAD','location.read'), ('STORE_HEAD','location.read'),
    ('STORE_TEAM','location.read'), ('PPIC_PLANNER','location.read'), ('FINANCE_ANALYST','location.read'),
    ('SYS_ADMIN','location.create'), ('DEMAND_PLANNER','location.create'),
    ('SYS_ADMIN','location.update'), ('DEMAND_PLANNER','location.update'),
    ('SYS_ADMIN','location.status_change'), ('DEMAND_PLANNER','location.status_change'),
    ('SYS_ADMIN','location.assign_om'), ('DEMAND_PLANNER','location.assign_om'), ('AREA_HEAD','location.assign_om'),
    ('SYS_ADMIN','location.closure.manage'), ('DEMAND_PLANNER','location.closure.manage'),
    ('OPS_MANAGER','location.closure.manage'), ('AREA_HEAD','location.closure.manage'),
    -- assortment / refdata / params
    ('SYS_ADMIN','assortment.manage'), ('DEMAND_PLANNER','assortment.manage'), ('OPS_MANAGER','assortment.manage'),
    ('SYS_ADMIN','refdata.manage'), ('DEMAND_PLANNER','refdata.manage'),
    ('SYS_ADMIN','param.read'), ('DEMAND_PLANNER','param.read'), ('CX_SPECIALIST','param.read'),
    ('OPS_MANAGER','param.read'), ('AREA_HEAD','param.read'), ('FINANCE_ANALYST','param.read'),
    ('SYS_ADMIN','param.update'), ('DEMAND_PLANNER','param.update'),
    -- order
    ('SYS_ADMIN','order.read'), ('DEMAND_PLANNER','order.read'), ('CX_SPECIALIST','order.read'),
    ('OPS_MANAGER','order.read'), ('AREA_HEAD','order.read'), ('STORE_HEAD','order.read'),
    ('PPIC_PLANNER','order.read'), ('FINANCE_ANALYST','order.read'),
    ('SYS_ADMIN','order.generate'), ('DEMAND_PLANNER','order.generate'),
    ('SYS_ADMIN','order.adjust_cx'), ('DEMAND_PLANNER','order.adjust_cx'), ('CX_SPECIALIST','order.adjust_cx'),
    ('SYS_ADMIN','order.adjust_om'), ('DEMAND_PLANNER','order.adjust_om'), ('OPS_MANAGER','order.adjust_om'), ('AREA_HEAD','order.adjust_om'),
    ('SYS_ADMIN','order.lock'), ('DEMAND_PLANNER','order.lock'),
    ('SYS_ADMIN','order.submit_ppic'), ('DEMAND_PLANNER','order.submit_ppic'),
    ('SYS_ADMIN','order.confirm_production'), ('PPIC_PLANNER','order.confirm_production'),
    -- counts / receiving / waste / movement
    ('SYS_ADMIN','count.submit'), ('OPS_MANAGER','count.submit'), ('STORE_HEAD','count.submit'), ('STORE_TEAM','count.submit'),
    ('SYS_ADMIN','count.approve'), ('OPS_MANAGER','count.approve'), ('AREA_HEAD','count.approve'), ('STORE_HEAD','count.approve'),
    ('SYS_ADMIN','receiving.confirm'), ('OPS_MANAGER','receiving.confirm'), ('STORE_HEAD','receiving.confirm'), ('STORE_TEAM','receiving.confirm'),
    ('SYS_ADMIN','waste.record'), ('OPS_MANAGER','waste.record'), ('STORE_HEAD','waste.record'), ('STORE_TEAM','waste.record'),
    ('SYS_ADMIN','movement.adjust'), ('DEMAND_PLANNER','movement.adjust'), ('OPS_MANAGER','movement.adjust'),
    -- accuracy / admin / audit / integration / export
    ('SYS_ADMIN','accuracy.read'), ('DEMAND_PLANNER','accuracy.read'), ('CX_SPECIALIST','accuracy.read'),
    ('OPS_MANAGER','accuracy.read'), ('AREA_HEAD','accuracy.read'), ('STORE_HEAD','accuracy.read'),
    ('PPIC_PLANNER','accuracy.read'), ('FINANCE_ANALYST','accuracy.read'),
    ('SYS_ADMIN','user.manage'), ('SYS_ADMIN','role.manage'),
    ('SYS_ADMIN','audit.read'), ('DEMAND_PLANNER','audit.read'), ('FINANCE_ANALYST','audit.read'),
    ('SYS_ADMIN','integration.manage'),
    ('SYS_ADMIN','export.data'), ('DEMAND_PLANNER','export.data'), ('CX_SPECIALIST','export.data'),
    ('OPS_MANAGER','export.data'), ('AREA_HEAD','export.data'), ('PPIC_PLANNER','export.data'), ('FINANCE_ANALYST','export.data'),
    -- EXECUTIVE (§7.3 footnote): read-only across order, accuracy, item, location
    ('EXECUTIVE','order.read'), ('EXECUTIVE','accuracy.read'), ('EXECUTIVE','item.read'), ('EXECUTIVE','location.read'),
    -- COMMISSARY_SUPERVISOR (§7.3 footnote): order.read, receiving.confirm, movement.adjust (scoped to commissary via branch scope)
    ('COMMISSARY_SUPERVISOR','order.read'), ('COMMISSARY_SUPERVISOR','receiving.confirm'), ('COMMISSARY_SUPERVISOR','movement.adjust')
) AS grants(role_code, permission_code)
JOIN core.role r ON r.role_code = grants.role_code
JOIN core.permission p ON p.permission_code = grants.permission_code;

-- =====================================================================
-- Minimal structural lookups referenced elsewhere in the schema/spec text
-- =====================================================================

-- §4.8: source systems named explicitly as examples in the spec's own DDL comment.
INSERT INTO core.source_system (source_code, label, system_type, is_active) VALUES
    ('MANUAL_UPLOAD', 'Manual file upload', 'FILE', TRUE),
    ('DR_SYSTEM',      'Delivery Receipt system', 'ERP', TRUE),
    ('POS_MAIN',       'Primary POS', 'POS', TRUE),
    ('GRABFOOD',       'GrabFood aggregator', 'AGGREGATOR', TRUE);

-- §4.3: base_uom defaults to 'pc'; §4.3 comment gives "sack -> kg, case -> sleeve -> piece"
-- as the worked conversion example.
INSERT INTO core.uom (uom_code, label, is_fractional) VALUES
    ('pc',     'Piece',  FALSE),
    ('kg',     'Kilogram', TRUE),
    ('sack',   'Sack',   FALSE),
    ('case',   'Case',   FALSE),
    ('sleeve', 'Sleeve', FALSE);

-- §4.4: 'CORRECTION' is the reason_code the immutability rule names explicitly
-- for offsetting ledger entries. Everything else is admin-owned (§5.7 rule 1).
INSERT INTO core.reason_code (reason_code, category, label, requires_note, is_active) VALUES
    ('CORRECTION', 'ADJUSTMENT', 'Correction (offsetting entry for a prior error)', TRUE, TRUE);

COMMIT;
