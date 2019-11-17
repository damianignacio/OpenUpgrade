# -*- coding: utf-8 -*-
# © 2016 Therp BV <http://therp.nl>
# Copyright 2016 Pedro M. Baeza <pedro.baeza@tecnativa.com>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

from openupgradelib import openupgrade

column_renames = {
    'delivery_grid_line': [
        ('price_type', None),
    ],
    # N/A
    # 'delivery_grid': [
    #     ('carrier_id', None),
    # ],
    'delivery_grid_country_rel': [
        ('grid_id', 'carrier_id'),
    ],
    'delivery_grid_state_rel': [
        ('grid_id', 'carrier_id'),
    ],
}

field_renames = [
    ('delivery.grid.line', 'delivery_grid_line', 'type', 'variable'),
    ('delivery.grid.line', 'delivery_grid_line', 'grid_id', 'carrier_id'),
]

column_copies = {
    'delivery_grid_line': [
        ('list_price', 'list_base_price', None),
    ],
}

table_renames = [
    # N/A
    # ('delivery_carrier', None),
    ('delivery_grid', None),
    ('delivery_grid_line', 'delivery_price_rule'),
    ('delivery_grid_country_rel', 'delivery_carrier_country_rel'),
    ('delivery_grid_state_rel', 'delivery_carrier_state_rel'),
]


def __NA__correct_object_references(cr):
    """Point sale order and stock picking to grid records (that will be
    renamed as carrier objects)."""
    openupgrade.lift_constraints(cr, 'sale_order', 'carrier_id')
    openupgrade.logged_query(
        cr, """
        UPDATE sale_order so SET carrier_id = dg.id
        FROM delivery_grid dg, delivery_carrier dc
        WHERE dg.carrier_id = dc.id AND so.carrier_id = dc.id
        """,
    )
    openupgrade.lift_constraints(cr, 'stock_picking', 'carrier_id')
    openupgrade.logged_query(
        cr, """
        UPDATE stock_picking sp SET carrier_id = dg.id
        FROM delivery_grid dg, delivery_carrier dc
        WHERE dg.carrier_id = dc.id AND sp.carrier_id = dc.id
        """,
    )


def correct_rule_prices(cr):
    """Version 8 only allows to put a fixed or variable price, not both.
    Now version 9 have a field for each option. We copy the value on both
    fields and zero the field that doesn't correspond to the version in 8.
    """
    openupgrade.copy_columns(cr, column_copies)
    cr.execute("""
        UPDATE delivery_grid_line
        SET list_price = 0
        WHERE {0} = 'fixed'
    """.format(openupgrade.get_legacy_name('price_type')))

    cr.execute("""
        UPDATE delivery_grid_line
        SET list_base_price = 0
        WHERE {0} = 'variable'
    """.format(openupgrade.get_legacy_name('price_type')))


def __NA__fill_missing_delivery_grid_records(cr):
    """Add records for delivery carriers without grid for keeping integrity."""
    openupgrade.logged_query(
        cr, """
        INSERT INTO delivery_grid
        (create_uid, create_date, name, sequence, carrier_id,
         write_uid, active, write_date)
        SELECT
            dc.create_uid, dc.create_date, dc.name, 1, dc.id,
            dc.write_uid, dc.active, dc.write_date
        FROM delivery_carrier dc
        LEFT JOIN delivery_grid dg ON dg.carrier_id = dc.id
        WHERE dg.id IS NULL"""
    )


def __NA__create_delivery_products(env):
    """As now delivery.carrier inherits by delegation from product.product,
    we need to create a specific product for each carrier, independently from
    the previous product that was assigned. If not, things like the carrier
    name will be taken from old product name, carriers will share products...

    To be executed before the renaming, but after filling missing grids.
    """
    # Pre-create product_id column
    env.cr.execute("ALTER TABLE delivery_grid ADD product_id INTEGER")
    # Add a product per carrier
    env.cr.execute(
        """SELECT dg.id, dc.name, dg.name
        FROM delivery_carrier dc, delivery_grid dg
        WHERE dc.id = dg.carrier_id"""
    )
    Product = env['product.product']
    for row in env.cr.fetchall():
        product = Product.create({
            'name': row[1] + ": " + row[2],
            'type': 'service',
        })
        env.cr.execute(
            "UPDATE delivery_grid SET product_id=%s WHERE id=%s",
            (product.id, row[0]),
        )


# Fields added to version 9.0
#  delivery_type     | character varying           | not null
#  fixed_price       | double precision            |
#  zip_to            | character varying           |
#  sequence          | integer                     |
#  shipping_enabled  | boolean                     |
#  zip_from          | character varying           |


def add_fields_to_delivery_carrier(cr):
    cr.execute("""ALTER TABLE delivery_carrier
        ADD delivery_type VARCHAR,
        ADD fixed_price DOUBLE PRECISION,
        ADD zip_to VARCHAR,
        ADD sequence INTEGER,
        ADD shipping_enabled BOOLEAN,
        ADD zip_from VARCHAR
    """)

    # set initial values
    cr.execute("""UPDATE delivery_carrier SET delivery_type = 'fixed',
        fixed_price = 0.0,
        sequence = 10,
        shipping_enabled = TRUE
    """)

    cr.execute("ALTER TABLE delivery_carrier ALTER COLUMN delivery_type SET NOT NULL")


def correct_grid_references(env):
    env.cr.execute("SELECT dg.id, dc.carrier_id FROM delivery_grid dg")

    # grid_id -> carrier_id
    mapping = {}
    for row in env.cr.fetchall():
        mapping[row[0]] = row[1]

    openupgrade.lift_constraints(env.cr, 'delivery_grid_line', 'carrier_id')
    openupgrade.lift_constraints(env.cr, 'delivery_grid_country_rel', 'carrier_id')
    openupgrade.lift_constraints(env.cr, 'delivery_grid_state_rel', 'carrier_id')

    for grid_id, carrier_id in mapping.items():
        env.cr.execute("UPDATE delivery_grid_line SET carrier_id = %s WHERE {0} = %s".format(
            openupgrade.get_legacy_name('grid_id')
        ), [carrier_id, grid_id])
        env.cr.execute("UPDATE delivery_grid_country_rel SET carrier_id = %s WHERE {0} = %s".format(
            openupgrade.get_legacy_name('grid_id')
        ), [carrier_id, grid_id])
        env.cr.execute("UPDATE delivery_grid_state_rel SET carrier_id = %s WHERE {0} = %s ".format(
            openupgrade.get_legacy_name('grid_id')
        ), [carrier_id, grid_id])


def mantain_grid_reference(cr):
    openupgrade.copy_columns(cr, {
        'delivery_grid_line': [
            ('grid_id', None, None),
        ],
        'delivery_grid_country_rel': [
            ('grid_id', None, None),
        ],
        'delivery_grid_state_rel': [
            ('grid_id', None, None),
        ],
    })


@openupgrade.migrate(use_env=True)
def migrate(env, version):
    cr = env.cr

    mantain_grid_reference(cr)

    # __NA__fill_missing_delivery_grid_records(cr)
    # __NA__create_delivery_products(env)
    # __NA__correct_object_references(cr)
    openupgrade.rename_columns(cr, column_renames)
    openupgrade.rename_fields(env, field_renames)

    correct_grid_references(env)
    add_fields_to_delivery_carrier(cr)
    correct_rule_prices(cr)

    openupgrade.rename_tables(cr, table_renames)
    openupgrade.rename_property(
        cr,
        'res.partner',
        'property_delivery_carrier',
        'property_delivery_carrier_id',
    )
