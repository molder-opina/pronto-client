-- Agregar tablas para asignación de mesas a meseros y solicitudes de transferencia
-- Permite gestión persistente de mesas por turno con sistema de transferencias

-- Tabla de asignaciones de mesa-mesero
CREATE TABLE IF NOT EXISTS waiter_table_assignments (
    id INTEGER PRIMARY KEY AUTO_INCREMENT,
    waiter_id INTEGER NOT NULL,
    table_id INTEGER NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT 1,
    assigned_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    unassigned_at TIMESTAMP NULL,
    notes TEXT,
    FOREIGN KEY (waiter_id) REFERENCES employees(id) ON DELETE CASCADE,
    FOREIGN KEY (table_id) REFERENCES tables(id) ON DELETE CASCADE,
    CONSTRAINT uq_waiter_table_active UNIQUE (waiter_id, table_id)
);

CREATE INDEX ix_waiter_table_assignment_waiter ON waiter_table_assignments(waiter_id);
CREATE INDEX ix_waiter_table_assignment_table ON waiter_table_assignments(table_id);
CREATE INDEX ix_waiter_table_assignment_active ON waiter_table_assignments(is_active);

-- Tabla de solicitudes de transferencia de mesas entre meseros
CREATE TABLE IF NOT EXISTS table_transfer_requests (
    id INTEGER PRIMARY KEY AUTO_INCREMENT,
    table_id INTEGER NOT NULL,
    from_waiter_id INTEGER NOT NULL,
    to_waiter_id INTEGER NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'pending',
    transfer_orders BOOLEAN NOT NULL DEFAULT 0,
    message TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    resolved_at TIMESTAMP NULL,
    resolved_by_employee_id INTEGER NULL,
    FOREIGN KEY (table_id) REFERENCES tables(id) ON DELETE CASCADE,
    FOREIGN KEY (from_waiter_id) REFERENCES employees(id) ON DELETE CASCADE,
    FOREIGN KEY (to_waiter_id) REFERENCES employees(id) ON DELETE CASCADE,
    FOREIGN KEY (resolved_by_employee_id) REFERENCES employees(id) ON DELETE SET NULL
);

CREATE INDEX ix_table_transfer_from_waiter ON table_transfer_requests(from_waiter_id);
CREATE INDEX ix_table_transfer_to_waiter ON table_transfer_requests(to_waiter_id);
CREATE INDEX ix_table_transfer_table ON table_transfer_requests(table_id);
CREATE INDEX ix_table_transfer_status ON table_transfer_requests(status);
CREATE INDEX ix_table_transfer_created ON table_transfer_requests(created_at);
