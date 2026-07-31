-- =====================================================================
--  Cocopan Inventory Management System (CIMS) — Seed Data
--  Target: PostgreSQL 16 (Cloud SQL)  ·  Run AFTER the DDL in SPEC v3 §4
--  Generated from the client's forecast workbook
--    (Updated Forecast Template_For July 30 to Aug 2_Ref Jun 29 to Jul 26.xlsx)
--
--  PROVENANCE
--    [REAL]    taken verbatim from the client workbook
--    [DERIVED] computed from workbook figures
--    [ASSUMED] our placeholder — MUST be confirmed with the client
--
--    Item codes, names, SRP, packaging, shelf life, MOQ, lifecycle remarks  [REAL]
--    Store codes, store names, average daily sales                          [REAL]
--    Areas, clusters, routes, geography, store formats, open dates          [ASSUMED]
--    Users, roles, permissions, parameters, calendar                        [ASSUMED]
--
--  KNOWN CONFLICT: SRP differs between the workbook's Pillow Pack Sched sheet
--  and the individual store tabs (e.g. Double Cheese Roll 15 vs 18; Cinnamon
--  Deluxe 20 vs 22). We seed the Pillow Pack Sched value as current and record
--  the store-tab value as a superseded price row so both are visible.
--  RESOLVE THIS WITH THE CLIENT BEFORE GO-LIVE.
-- =====================================================================

BEGIN;
SET search_path TO core, public;

-- Audit context for this seed run
SELECT set_config('app.user_id',   '1', false);
SELECT set_config('app.user_email','seed@cocopan.ph', false);
SELECT set_config('app.request_id', gen_random_uuid()::text, false);
SELECT set_config('app.unrestricted','on', false);

-- ---------------------------------------------------------------------
-- 1. Units of measure                                          [ASSUMED]
-- ---------------------------------------------------------------------
INSERT INTO uom (uom_code, label, is_fractional) VALUES
  ('pc','Piece',FALSE),('pack','Pack',FALSE),('tray','Tray',FALSE),
  ('case','Case',FALSE),('kg','Kilogram',TRUE),('g','Gram',TRUE)
ON CONFLICT DO NOTHING;

-- ---------------------------------------------------------------------
-- 2. Geography — PH hierarchy                                  [ASSUMED]
-- ---------------------------------------------------------------------
INSERT INTO geography (geo_code, parent_code, geo_level, label) VALUES
  ('NCR',   NULL,  'REGION','National Capital Region'),
  ('R3',    NULL,  'REGION','Region III - Central Luzon'),
  ('R4A',   NULL,  'REGION','Region IV-A - CALABARZON'),
  ('BULACAN','R3', 'PROVINCE','Bulacan'),
  ('RIZAL', 'R4A', 'PROVINCE','Rizal'),
  ('LAGUNA','R4A', 'PROVINCE','Laguna'),
  ('CAVITE','R4A', 'PROVINCE','Cavite'),
  ('MNL','NCR','CITY','Manila'),      ('QZC','NCR','CITY','Quezon City'),
  ('CAL','NCR','CITY','Caloocan'),    ('MLB','NCR','CITY','Malabon'),
  ('NAV','NCR','CITY','Navotas'),     ('VAL','NCR','CITY','Valenzuela'),
  ('MKT','NCR','CITY','Makati'),      ('TAG','NCR','CITY','Taguig'),
  ('PTR','NCR','CITY','Pateros'),     ('PSG','NCR','CITY','Pasig'),
  ('MND','NCR','CITY','Mandaluyong'), ('SJN','NCR','CITY','San Juan'),
  ('MRK','NCR','CITY','Marikina'),    ('PSY','NCR','CITY','Pasay'),
  ('PRQ','NCR','CITY','Paranaque'),   ('LSP','NCR','CITY','Las Pinas'),
  ('MTL','NCR','CITY','Muntinlupa')
ON CONFLICT DO NOTHING;

-- ---------------------------------------------------------------------
-- 3. Areas, clusters, routes                                   [ASSUMED]
--    Cluster drives new-store forecasting analogs (SPEC 8.5).
-- ---------------------------------------------------------------------
INSERT INTO area (area_code, label) VALUES
  ('AREA_MANILA','Manila'),
  ('AREA_QC','Quezon City'),
  ('AREA_CAMANAVA','Caloocan-Malabon-Navotas'),
  ('AREA_VALENZUELA','Valenzuela'),
  ('AREA_MAKATI_TAGUIG','Makati-Taguig-Pateros'),
  ('AREA_PASIG_MANDA','Pasig-Mandaluyong-San Juan-Marikina'),
  ('AREA_SOUTH_NCR','Pasay-Paranaque-Las Pinas-Muntinlupa'),
  ('AREA_RIZAL','Rizal'),
  ('AREA_BULACAN','Bulacan'),
  ('AREA_SOUTH_LUZON','Laguna-Cavite')
ON CONFLICT DO NOTHING;

INSERT INTO cluster (cluster_code, label, description) VALUES
  ('RESIDENTIAL','Residential','Neighbourhood barangay store, steady weekday pattern'),
  ('HIGH_TRAFFIC_24H','High Traffic 24H','High volume, extended or 24-hour trading'),
  ('TRANSPORT_HUB','Transport Hub','LRT/terminal adjacent; sharp AM and PM peaks'),
  ('PUBLIC_MARKET','Public Market','Market-adjacent; early morning skew'),
  ('SUPERMARKET_CONCESSION','Supermarket Concession','Inside a host supermarket; follows host hours'),
  ('COMMERCIAL_STRIP','Commercial Strip','Office/commercial corridor; weekday skew')
ON CONFLICT DO NOTHING;

-- Routes reflect the workbook's two dispatch waves (Before 8am / After 8am)
INSERT INTO route (route_code, label, dispatch_sequence) VALUES
  ('W1_NORTH','Wave 1 - North (before 8am)',1),
  ('W1_SOUTH','Wave 1 - South (before 8am)',2),
  ('W1_EAST','Wave 1 - East (before 8am)',3),
  ('W2_NORTH','Wave 2 - North (after 8am)',4),
  ('W2_SOUTH','Wave 2 - South (after 8am)',5),
  ('W2_EAST','Wave 2 - East (after 8am)',6),
  ('PROV_BUL','Provincial - Bulacan',7),
  ('PROV_STH','Provincial - Rizal/Laguna/Cavite',8)
ON CONFLICT DO NOTHING;

-- ---------------------------------------------------------------------
-- 4. Item categories                                           [ASSUMED]
-- ---------------------------------------------------------------------
INSERT INTO item_category (category_code, parent_code, label, sort_order) VALUES
  ('BREAD',NULL,'Bread',1),
  ('BREAD_SWEET','BREAD','Sweet Bread',1),
  ('BREAD_SAVORY','BREAD','Savory Bread',2),
  ('PANDESAL','BREAD','Pandesal',3),
  ('LOAF','BREAD','Loaf',4),
  ('BUN_PREMIUM','BREAD','Premium Bun',5),
  ('ROLL_CINNAMON','BREAD','Cinnamon Roll',6),
  ('DONUT',NULL,'Donut',2),
  ('CAKE_MUFFIN',NULL,'Cake & Muffin',3)
ON CONFLICT DO NOTHING;

-- ---------------------------------------------------------------------
-- 5. Item master                                                  [REAL]
--    Source: Pillow Pack Sched + Parameters (MOQ) sheets.
--    shelf_life_days > 0  => MULTI_DAY carryover policy (SPEC 9 Step 6)
--    Loaves and pandesal packs are MOQ-exempt per the client's email.
-- ---------------------------------------------------------------------
INSERT INTO item (item_code, item_type, desc_dr, desc_offtake, display_name,
                  category_code, base_uom, packaging, shelf_life_days,
                  replen_policy, moq, moq_exempt, order_multiple,
                  lifecycle_status, status_remark) VALUES
  ('CP001','FINISHED_GOOD','PAN DE COCO','PAN DE COCO','Pan De Coco','BREAD_SWEET','pc','MACHINE_WRAPPED',3,'MULTI_DAY',16,FALSE,1,'PILOT','Pilot Breads in Pillow Packaging'),
  ('CP004','FINISHED_GOOD','CHEESE ROLL','CHEESE ROLL','Cheese Roll','BREAD_SAVORY','pc','MACHINE_WRAPPED',4,'MULTI_DAY',16,FALSE,1,'PILOT','Pilot Breads in Pillow Packaging'),
  ('CP006','FINISHED_GOOD','SPANISH BREAD','SPANISH BREAD','Spanish Bread','BREAD_SWEET','pc','MACHINE_WRAPPED',4,'MULTI_DAY',16,FALSE,1,'PILOT','Pilot Breads in Pillow Packaging'),
  ('CP008','FINISHED_GOOD','CHOCO ROLL','CHOCO ROLL','Choco Roll','BREAD_SWEET','pc','MANUAL_PACKING',0,'SAME_DAY',12,FALSE,1,'ACTIVE',NULL),
  ('CP025','FINISHED_GOOD','BANANA BREAD','BANANA BREAD','Banana Bread','CAKE_MUFFIN','pc','MANUAL_PACKING',4,'MULTI_DAY',12,FALSE,1,'ACTIVE',NULL),
  ('CP028','FINISHED_GOOD','CINNAMON CLASSIC','CINNAMON CLASSIC','Cinnamon Classic','ROLL_CINNAMON','pc','MANUAL_PACKING',3,'MULTI_DAY',16,FALSE,1,'DO_NOT_INCLUDE_YET','Do Not Include yet: Required Additional Manpower'),
  ('CP034','FINISHED_GOOD','SUGAR DONUT','SUGAR DONUT','Sugar Donut','DONUT','pc','MACHINE_WRAPPED',4,'MULTI_DAY',16,FALSE,1,'DO_NOT_INCLUDE_YET','Do Not Include yet - Snow Sugar Donut'),
  ('CP060','FINISHED_GOOD','COFFEE BUN','COFFEE BUN','Coffee Bun','BUN_PREMIUM','pc','MACHINE_WRAPPED',4,'MULTI_DAY',12,FALSE,1,'ACTIVE',NULL),
  ('CP061','FINISHED_GOOD','CHEESE BURST DONUT','CHEESE BURST DONUT','Cheese Burst Donut','DONUT','pc','MANUAL_PACKING',0,'SAME_DAY',10,FALSE,1,'ACTIVE',NULL),
  ('CP062','FINISHED_GOOD','MILKY CHEESE DONUT','MILKY CHEESE DONUT','Milky Cheese Donut','DONUT','pc','MACHINE_WRAPPED',4,'MULTI_DAY',12,FALSE,1,'DO_NOT_INCLUDE_YET','Do Not Include yet: Waiting for Plastic Sachet Packing'),
  ('CP074','FINISHED_GOOD','PAN DE FLOSS ORIG','PAN DE FLOSS ORIG','Pan De Floss Orig','BUN_PREMIUM','pc','MACHINE_WRAPPED',4,'MULTI_DAY',12,FALSE,1,'ACTIVE',NULL),
  ('CP075','FINISHED_GOOD','PAN DE FLOSS SPICY','PAN DE FLOSS SPICY','Pan De Floss Spicy','BUN_PREMIUM','pc','MACHINE_WRAPPED',4,'MULTI_DAY',12,FALSE,1,'ACTIVE',NULL),
  ('CP076','FINISHED_GOOD','GLAZED DONUT','GLAZED DONUT','Glazed Donut','DONUT','pc','MANUAL_PACKING',3,'MULTI_DAY',16,FALSE,1,'DO_NOT_INCLUDE_YET','Do Not Include yet: Waiting for White Frost Launch'),
  ('CP077','FINISHED_GOOD','CHOCO CHEESE DONUT','CHOCO CHEESE DONUT','Choco Cheese Donut','DONUT','pc','MACHINE_WRAPPED',4,'MULTI_DAY',12,FALSE,1,'DO_NOT_INCLUDE_YET','Do Not Include yet: Waiting for Plastic Sachet Packing'),
  ('CP088','FINISHED_GOOD','ITALIAN CHEESE ROLL','ITALIAN CHEESE ROLL','Italian Cheese Roll','BREAD_SAVORY','pc','MACHINE_WRAPPED',4,'MULTI_DAY',12,FALSE,1,'ACTIVE',NULL),
  ('CP095','FINISHED_GOOD','CHEESY HAM ROLL','CHEESY HAM ROLL','Cheesy Ham Roll','BREAD_SAVORY','pc','MACHINE_WRAPPED',4,'MULTI_DAY',12,FALSE,1,'ACTIVE',NULL),
  ('CP096','FINISHED_GOOD','CHOCO CHIP MUFFIN','CHOCO CHIP MUFFIN','Choco Chip Muffin','CAKE_MUFFIN','pc','MACHINE_WRAPPED',4,'MULTI_DAY',10,FALSE,1,'ACTIVE',NULL),
  ('CP097','FINISHED_GOOD','RAISIN LOAF','RAISIN LOAF','Raisin Loaf','LOAF','pc','MANUAL_PACKING',4,'MULTI_DAY',0,TRUE,1,'ACTIVE','Manual Packing (AS IS)'),
  ('CP099','FINISHED_GOOD','ITALIAN HERB LOAF','ITALIAN HERB LOAF','Italian Herb Loaf','LOAF','pc','MANUAL_PACKING',4,'MULTI_DAY',0,TRUE,1,'ACTIVE','Manual Packing (AS IS)'),
  ('CP102','FINISHED_GOOD','CHEESY SAUSAGE ROLL','CHEESY SAUSAGE ROLL','Cheesy Sausage Roll','BREAD_SAVORY','pc','MACHINE_WRAPPED',2,'MULTI_DAY',10,FALSE,1,'ACTIVE',NULL),
  ('CP103','FINISHED_GOOD','BLUEBERRY MUFFIN','BLUEBERRY MUFFIN','Blueberry Muffin','CAKE_MUFFIN','pc','MACHINE_WRAPPED',4,'MULTI_DAY',10,FALSE,1,'ACTIVE',NULL),
  ('CP104','FINISHED_GOOD','PAN DE SAL (10 PCS)','PAN DE SAL (10 PCS)','Pan De Sal (10 Pcs)','PANDESAL','pc','MANUAL_PACKING',4,'MULTI_DAY',0,TRUE,1,'ACTIVE','Manual Packing (AS IS)'),
  ('CP105','FINISHED_GOOD','CHOCO FROST DONUT','CHOCO FROST DONUT','Choco Frost Donut','DONUT','pc','MACHINE_WRAPPED',4,'MULTI_DAY',12,FALSE,1,'ACTIVE',NULL),
  ('CP106','FINISHED_GOOD','STRWBRY SPRNKE DONUT','STRWBRY SPRNKE DONUT','Strwbry Sprnke Donut','DONUT','pc','MACHINE_WRAPPED',4,'MULTI_DAY',12,FALSE,1,'ACTIVE',NULL),
  ('CP107','FINISHED_GOOD','DOUBLE CHEESE ROLL','DOUBLE CHEESE ROLL','Double Cheese Roll','BREAD_SAVORY','pc','MACHINE_WRAPPED',4,'MULTI_DAY',16,FALSE,1,'PILOT','Pilot Breads in Pillow Packaging'),
  ('CP109','FINISHED_GOOD','TUNA BUN','TUNA BUN','Tuna Bun','BUN_PREMIUM','pc','MACHINE_WRAPPED',3,'MULTI_DAY',10,FALSE,1,'ACTIVE',NULL),
  ('CP110','FINISHED_GOOD','CINNAMON DELUXE','CINNAMON DELUXE','Cinnamon Deluxe','ROLL_CINNAMON','pc','MANUAL_PACKING',3,'MULTI_DAY',16,FALSE,1,'DO_NOT_INCLUDE_YET','Do Not Include yet: Required Additional Manpower'),
  ('CP112','FINISHED_GOOD','CHICKEN ASADO BUN','CHICKEN ASADO BUN','Chicken Asado Bun','BUN_PREMIUM','pc','MANUAL_PACKING',0,'SAME_DAY',10,FALSE,1,'ACTIVE',NULL),
  ('CP113','FINISHED_GOOD','CHOCO CREAM PAN','CHOCO CREAM PAN','Choco Cream Pan','BREAD_SWEET','pc','MACHINE_WRAPPED',4,'MULTI_DAY',16,FALSE,1,'PILOT','Pilot Breads in Pillow Packaging'),
  ('CP116','FINISHED_GOOD','P PAN BUTTER SUGAR','P PAN BUTTER SUGAR','P Pan Butter Sugar','PANDESAL','pc','MACHINE_WRAPPED',3,'MULTI_DAY',0,TRUE,1,'TEMPORARILY_NOT_AVAILABLE','Temporarily Not Available'),
  ('CP117','FINISHED_GOOD','P PAN GARLIC BUTTER','P PAN GARLIC BUTTER','P Pan Garlic Butter','PANDESAL','pc','MACHINE_WRAPPED',3,'MULTI_DAY',0,TRUE,1,'TEMPORARILY_NOT_AVAILABLE','Temporarily Not Available'),
  ('CP118','FINISHED_GOOD','CORNEDBEEF PANDESAL','CORNEDBEEF PANDESAL','Cornedbeef Pandesal','PANDESAL','pc','MACHINE_WRAPPED',3,'MULTI_DAY',10,FALSE,1,'ACTIVE',NULL),
  ('CP120','FINISHED_GOOD','OREO CREAM PAN','OREO CREAM PAN','Oreo Cream Pan','BREAD_SWEET','pc','MACHINE_WRAPPED',4,'MULTI_DAY',16,FALSE,1,'PILOT','Pilot Breads in Pillow Packaging'),
  ('CP121','FINISHED_GOOD','STRAWBERRY JELLY PAN','STRAWBERRY JELLY PAN','Strawberry Jelly Pan','BREAD_SWEET','pc','MACHINE_WRAPPED',4,'MULTI_DAY',16,FALSE,1,'PILOT','Pilot Breads in Pillow Packaging')
ON CONFLICT (item_code) DO NOTHING;

-- Aliases: the DR system and the Offtake (sales) system use different names.
INSERT INTO item_alias (item_code, source_code, alias_text)
SELECT item_code,'DR_SYSTEM',desc_dr FROM item
UNION ALL
SELECT item_code,'POS_MAIN',desc_offtake FROM item
ON CONFLICT DO NOTHING;

-- ---------------------------------------------------------------------
-- 7. Branch master — 121 branches                                 [REAL]
--    Codes, names and average daily sales come from the workbook's ADS tab.
--    area / cluster / route / geo / format / open_date are [ASSUMED] and
--    must be confirmed. Branches with zero ADS are seeded PRE_OPENING;
--    the 8 tabs with no ADS row are seeded PLANNED.
--    NOTE: is_active and is_orderable are GENERATED — never set by hand.
-- ---------------------------------------------------------------------
INSERT INTO location (location_code, location_type, location_name, store_format,
                      cluster_code, area_code, route_code, geo_code, status,
                      open_date, ramp_weeks, display_capacity_units) VALUES
  ('CMSY-01','COMMISSARY','Central Commissary','STANDALONE',NULL,NULL,NULL,'MNL','ACTIVE','2022-06-01',0,NULL),
  ('KLN','BRANCH','Kalentong','STANDALONE','RESIDENTIAL','AREA_PASIG_MANDA','W1_EAST','PSG','ACTIVE','2024-01-15',8,1400),
  ('PAC','BRANCH','Paco','STANDALONE','RESIDENTIAL','AREA_MANILA','W1_SOUTH','MNL','ACTIVE','2024-01-15',8,1400),
  ('SNL','BRANCH','San Lazaro','STANDALONE','RESIDENTIAL','AREA_MANILA','W1_SOUTH','MNL','ACTIVE','2024-01-15',8,1200),
  ('PED','BRANCH','Pedro Gil','STANDALONE','RESIDENTIAL','AREA_MANILA','W1_SOUTH','MNL','ACTIVE','2024-01-15',8,950),
  ('TEJ','BRANCH','Tejeros','STANDALONE','RESIDENTIAL','AREA_MANILA','W1_SOUTH','MNL','ACTIVE','2024-01-15',8,1600),
  ('COM','BRANCH','Comembo','STANDALONE','RESIDENTIAL','AREA_MAKATI_TAGUIG','W1_SOUTH','TAG','ACTIVE','2024-01-15',8,1750),
  ('AGL','BRANCH','Aglipay','STANDALONE','RESIDENTIAL','AREA_MANILA','W1_SOUTH','MNL','ACTIVE','2024-01-15',8,1500),
  ('KLT','BRANCH','Kalentong 2','STANDALONE','RESIDENTIAL','AREA_PASIG_MANDA','W1_EAST','PSG','ACTIVE','2024-01-15',8,950),
  ('MER','BRANCH','Merville','STANDALONE','RESIDENTIAL','AREA_SOUTH_NCR','W2_SOUTH','PRQ','ACTIVE','2024-01-15',8,1400),
  ('GUA','BRANCH','Guadalupe','STANDALONE','RESIDENTIAL','AREA_MAKATI_TAGUIG','W1_SOUTH','TAG','ACTIVE','2024-01-15',8,1950),
  ('CMR','BRANCH','CM Recto','STANDALONE','PUBLIC_MARKET','AREA_MANILA','W1_SOUTH','MNL','ACTIVE','2024-01-15',8,1750),
  ('BLU','BRANCH','Blumentritt','STANDALONE','RESIDENTIAL','AREA_MANILA','W1_SOUTH','MNL','RAMP_UP','2026-06-15',8,650),
  ('ANO','BRANCH','Anonas','STANDALONE','HIGH_TRAFFIC_24H','AREA_QC','W1_NORTH','QZC','ACTIVE','2024-01-15',8,2700),
  ('SAC','BRANCH','Sixto Antonio','STANDALONE','RESIDENTIAL','AREA_PASIG_MANDA','W1_EAST','PSG','ACTIVE','2024-01-15',8,1250),
  ('KAT','BRANCH','Katuparan','STANDALONE','RESIDENTIAL','AREA_MAKATI_TAGUIG','W1_SOUTH','TAG','ACTIVE','2024-01-15',8,1450),
  ('QUA','BRANCH','Quiapo','STANDALONE','PUBLIC_MARKET','AREA_MANILA','W1_SOUTH','MNL','ACTIVE','2024-01-15',8,1500),
  ('NOV','BRANCH','Nova Proper','STANDALONE','RESIDENTIAL','AREA_QC','W1_NORTH','QZC','PRE_OPENING',NULL,8,NULL),
  ('PST','BRANCH','Pinagsama','STANDALONE','RESIDENTIAL','AREA_MAKATI_TAGUIG','W1_SOUTH','TAG','ACTIVE','2024-01-15',8,1350),
  ('EMC','BRANCH','Ever Caloocan','CONCESSION','SUPERMARKET_CONCESSION','AREA_CAMANAVA','W1_NORTH','CAL','ACTIVE','2024-01-15',8,950),
  ('MOO','BRANCH','Moonwalk','STANDALONE','RESIDENTIAL','AREA_SOUTH_NCR','W2_SOUTH','PRQ','ACTIVE','2024-01-15',8,850),
  ('LAH','BRANCH','La Huerta','STANDALONE','RESIDENTIAL','AREA_SOUTH_NCR','W2_SOUTH','PRQ','ACTIVE','2024-01-15',8,1150),
  ('CAA','BRANCH','CAA Las Pinas','STANDALONE','RESIDENTIAL','AREA_SOUTH_NCR','W2_SOUTH','PRQ','ACTIVE','2024-01-15',8,1100),
  ('VIL','BRANCH','Villongco','STANDALONE','RESIDENTIAL','AREA_SOUTH_NCR','W2_SOUTH','PRQ','ACTIVE','2024-01-15',8,1200),
  ('PLL','BRANCH','Pulang Lupa','STANDALONE','RESIDENTIAL','AREA_SOUTH_NCR','W2_SOUTH','PRQ','RAMP_UP','2026-06-15',8,800),
  ('PBP','BRANCH','Pinagbuhatan','STANDALONE','RESIDENTIAL','AREA_PASIG_MANDA','W1_EAST','PSG','ACTIVE','2024-01-15',8,1100),
  ('MUN','BRANCH','Munoz','STANDALONE','RESIDENTIAL','AREA_QC','W1_NORTH','QZC','ACTIVE','2024-01-15',8,1950),
  ('PIO','BRANCH','PIO Valenzuela','STANDALONE','RESIDENTIAL','AREA_VALENZUELA','W2_NORTH','VAL','ACTIVE','2024-01-15',8,1150),
  ('SAR','BRANCH','Sarmiento Nova','STANDALONE','RESIDENTIAL','AREA_QC','W1_NORTH','QZC','ACTIVE','2024-01-15',8,1300),
  ('EMN','BRANCH','Ever Navotas','CONCESSION','SUPERMARKET_CONCESSION','AREA_CAMANAVA','W1_NORTH','CAL','ACTIVE','2024-01-15',8,1450),
  ('MAY','BRANCH','Maysilo','STANDALONE','RESIDENTIAL','AREA_CAMANAVA','W1_NORTH','CAL','ACTIVE','2024-01-15',8,1450),
  ('GAS','BRANCH','Gastambide','STANDALONE','COMMERCIAL_STRIP','AREA_MANILA','W1_SOUTH','MNL','ACTIVE','2024-01-15',8,1650),
  ('DGP','BRANCH','Don Galo','STANDALONE','RESIDENTIAL','AREA_SOUTH_NCR','W2_SOUTH','PRQ','PRE_OPENING',NULL,8,NULL),
  ('BIC','BRANCH','Vicas','STANDALONE','RESIDENTIAL','AREA_VALENZUELA','W2_NORTH','VAL','ACTIVE','2024-01-15',8,1400),
  ('GIL','BRANCH','Buendia 1','STANDALONE','COMMERCIAL_STRIP','AREA_MAKATI_TAGUIG','W1_SOUTH','TAG','ACTIVE','2024-01-15',8,1550),
  ('SIG','BRANCH','Signal','STANDALONE','RESIDENTIAL','AREA_MAKATI_TAGUIG','W1_SOUTH','TAG','ACTIVE','2024-01-15',8,1500),
  ('TUL','BRANCH','Talon Uno','STANDALONE','RESIDENTIAL','AREA_SOUTH_NCR','W2_SOUTH','PRQ','ACTIVE','2024-01-15',8,1600),
  ('MUR','BRANCH','Murphy','STANDALONE','RESIDENTIAL','AREA_QC','W1_NORTH','QZC','ACTIVE','2024-01-15',8,1600),
  ('KAU','BRANCH','Kaunlaran','STANDALONE','RESIDENTIAL','AREA_CAMANAVA','W1_NORTH','CAL','PRE_OPENING',NULL,8,NULL),
  ('KAN','BRANCH','Kanlaon - Bagong Silang','STANDALONE','RESIDENTIAL','AREA_CAMANAVA','W1_NORTH','CAL','ACTIVE','2024-01-15',8,1500),
  ('BAC','BRANCH','Baclaran','STANDALONE','RESIDENTIAL','AREA_SOUTH_NCR','W2_SOUTH','PRQ','PRE_OPENING',NULL,8,NULL),
  ('VMC','BRANCH','Victory Mall Caloocan','CONCESSION','SUPERMARKET_CONCESSION','AREA_CAMANAVA','W1_NORTH','CAL','ACTIVE','2024-01-15',8,2000),
  ('MPC','BRANCH','Maypajo','STANDALONE','RESIDENTIAL','AREA_CAMANAVA','W1_NORTH','CAL','ACTIVE','2024-01-15',8,1250),
  ('CAL','BRANCH','Calderon - Sta. Ana','STANDALONE','RESIDENTIAL','AREA_MANILA','W1_SOUTH','MNL','ACTIVE','2024-01-15',8,1300),
  ('PAT','BRANCH','Pateros','STANDALONE','RESIDENTIAL','AREA_MAKATI_TAGUIG','W1_SOUTH','TAG','ACTIVE','2024-01-15',8,1450),
  ('EME','BRANCH','Ever 11th Avenue','CONCESSION','SUPERMARKET_CONCESSION','AREA_CAMANAVA','W1_NORTH','CAL','ACTIVE','2024-01-15',8,1300),
  ('CUM','BRANCH','Concepcion Uno','STANDALONE','RESIDENTIAL','AREA_MANILA','W1_SOUTH','MNL','ACTIVE','2024-01-15',8,1800),
  ('PTW','BRANCH','Palatiw','STANDALONE','RESIDENTIAL','AREA_PASIG_MANDA','W1_EAST','PSG','ACTIVE','2024-01-15',8,1350),
  ('BUE','BRANCH','Buendia 2','STANDALONE','COMMERCIAL_STRIP','AREA_QC','W1_NORTH','QZC','RAMP_UP','2026-06-15',8,450),
  ('MEY','BRANCH','Meycauayan','STANDALONE','RESIDENTIAL','AREA_BULACAN','PROV_BUL','BULACAN','ACTIVE','2024-01-15',8,1800),
  ('VI2','BRANCH','Villongco II','STANDALONE','RESIDENTIAL','AREA_SOUTH_NCR','W2_SOUTH','PRQ','PRE_OPENING',NULL,8,NULL),
  ('PS2','BRANCH','Pinagsama II - AFP','STANDALONE','RESIDENTIAL','AREA_MAKATI_TAGUIG','W1_SOUTH','TAG','ACTIVE','2024-01-15',8,1600),
  ('NAV','BRANCH','Naval Malabon','STANDALONE','RESIDENTIAL','AREA_CAMANAVA','W1_NORTH','CAL','ACTIVE','2024-01-15',8,1250),
  ('KAB','BRANCH','Victor Medina','STANDALONE','RESIDENTIAL','AREA_CAMANAVA','W1_NORTH','CAL','ACTIVE','2024-01-15',8,950),
  ('BFH','BRANCH','BF Holy Spirit','STANDALONE','RESIDENTIAL','AREA_QC','W1_NORTH','QZC','ACTIVE','2024-01-15',8,1400),
  ('BAG','BRANCH','Bagumbong','STANDALONE','RESIDENTIAL','AREA_CAMANAVA','W1_NORTH','CAL','PRE_OPENING',NULL,8,NULL),
  ('SAM','BRANCH','Luzon','STANDALONE','RESIDENTIAL','AREA_MANILA','W1_SOUTH','MNL','ACTIVE','2024-01-15',8,1400),
  ('PEM','BRANCH','Pembo','STANDALONE','RESIDENTIAL','AREA_MAKATI_TAGUIG','W1_SOUTH','TAG','ACTIVE','2024-01-15',8,1350),
  ('CSM','BRANCH','Citisquare Malabon','CONCESSION','SUPERMARKET_CONCESSION','AREA_CAMANAVA','W1_NORTH','CAL','ACTIVE','2024-01-15',8,1900),
  ('SQC','BRANCH','Sta. Quiteria','STANDALONE','RESIDENTIAL','AREA_CAMANAVA','W1_NORTH','CAL','ACTIVE','2024-01-15',8,1250),
  ('LTX','BRANCH','Litex','STANDALONE','RESIDENTIAL','AREA_QC','W1_NORTH','QZC','ACTIVE','2024-01-15',8,1000),
  ('FUG','BRANCH','Fugoso','STANDALONE','RESIDENTIAL','AREA_MANILA','W1_SOUTH','MNL','PRE_OPENING',NULL,8,NULL),
  ('NDS','BRANCH','N. Domingo','STANDALONE','RESIDENTIAL','AREA_PASIG_MANDA','W1_EAST','PSG','ACTIVE','2024-01-15',8,1500),
  ('LSB','BRANCH','LRT Blumentritt','STANDALONE','TRANSPORT_HUB','AREA_MANILA','W1_SOUTH','MNL','ACTIVE','2024-01-15',8,1350),
  ('GTD','BRANCH','Gen T. De Leon','STANDALONE','RESIDENTIAL','AREA_VALENZUELA','W2_NORTH','VAL','ACTIVE','2024-01-15',8,1600),
  ('KAM','BRANCH','Kamuning','STANDALONE','COMMERCIAL_STRIP','AREA_QC','W1_NORTH','QZC','ACTIVE','2024-01-15',8,1300),
  ('PTT','BRANCH','Putatan','STANDALONE','RESIDENTIAL','AREA_SOUTH_NCR','W2_SOUTH','PRQ','ACTIVE','2024-01-15',8,1850),
  ('CAQ','BRANCH','Congressional','STANDALONE','RESIDENTIAL','AREA_QC','W1_NORTH','QZC','ACTIVE','2024-01-15',8,1050),
  ('NRL','BRANCH','Naga Road','STANDALONE','RESIDENTIAL','AREA_SOUTH_NCR','W2_SOUTH','PRQ','ACTIVE','2024-01-15',8,900),
  ('TAY','BRANCH','Taytay','STANDALONE','RESIDENTIAL','AREA_RIZAL','PROV_STH','RIZAL','ACTIVE','2024-01-15',8,1650),
  ('DPA','BRANCH','Dela Paz Antipolo','STANDALONE','RESIDENTIAL','AREA_RIZAL','PROV_STH','RIZAL','ACTIVE','2024-01-15',8,1550),
  ('MLT','BRANCH','Malinta','STANDALONE','RESIDENTIAL','AREA_VALENZUELA','W2_NORTH','VAL','ACTIVE','2024-01-15',8,1500),
  ('MBY','BRANCH','Malibay','STANDALONE','RESIDENTIAL','AREA_SOUTH_NCR','W2_SOUTH','PRQ','ACTIVE','2024-01-15',8,1450),
  ('POB','BRANCH','Polo','STANDALONE','HIGH_TRAFFIC_24H','AREA_VALENZUELA','W2_NORTH','VAL','ACTIVE','2024-01-15',8,2100),
  ('BTS','BRANCH','Batasan','STANDALONE','RESIDENTIAL','AREA_QC','W1_NORTH','QZC','ACTIVE','2024-01-15',8,1650),
  ('PBR','BRANCH','Binangonan','STANDALONE','RESIDENTIAL','AREA_RIZAL','PROV_STH','RIZAL','ACTIVE','2024-01-15',8,900),
  ('EVA','BRANCH','Evacom','STANDALONE','RESIDENTIAL','AREA_PASIG_MANDA','W1_EAST','PSG','ACTIVE','2024-01-15',8,1100),
  ('LGQ','BRANCH','Galas','STANDALONE','RESIDENTIAL','AREA_QC','W1_NORTH','QZC','ACTIVE','2024-01-15',8,1200),
  ('MBC','BRANCH','Morning Breeze','STANDALONE','HIGH_TRAFFIC_24H','AREA_CAMANAVA','W1_NORTH','CAL','ACTIVE','2024-01-15',8,2550),
  ('LRP','BRANCH','Loreto','STANDALONE','RESIDENTIAL','AREA_PASIG_MANDA','W1_EAST','PSG','ACTIVE','2024-01-15',8,1350),
  ('BDM','BRANCH','Barangka','STANDALONE','RESIDENTIAL','AREA_PASIG_MANDA','W1_EAST','PSG','ACTIVE','2024-01-15',8,1400),
  ('ESP','BRANCH','Edsa Pasay','STANDALONE','COMMERCIAL_STRIP','AREA_SOUTH_NCR','W2_SOUTH','PRQ','ACTIVE','2024-01-15',8,1100),
  ('IMA','BRANCH','iMall','CONCESSION','SUPERMARKET_CONCESSION','AREA_QC','W1_NORTH','QZC','ACTIVE','2024-01-15',8,2600),
  ('SRP','BRANCH','Sixto Rosario','STANDALONE','RESIDENTIAL','AREA_PASIG_MANDA','W1_EAST','PSG','ACTIVE','2024-01-15',8,1200),
  ('SHO','BRANCH','Shoe Avenue','STANDALONE','RESIDENTIAL','AREA_PASIG_MANDA','W1_EAST','PSG','ACTIVE','2024-01-15',8,1550),
  ('ASM','BRANCH','Altura Sta Mesa','STANDALONE','RESIDENTIAL','AREA_MANILA','W1_SOUTH','MNL','ACTIVE','2024-01-15',8,1700),
  ('SMV','BRANCH','Gov Santiago Valenzuela','STANDALONE','RESIDENTIAL','AREA_VALENZUELA','W2_NORTH','VAL','ACTIVE','2024-01-15',8,1400),
  ('PCQ','BRANCH','Pinatubo Cubao','STANDALONE','COMMERCIAL_STRIP','AREA_QC','W1_NORTH','QZC','ACTIVE','2024-01-15',8,1150),
  ('EPM','BRANCH','Evanglista','STANDALONE','RESIDENTIAL','AREA_PASIG_MANDA','W1_EAST','PSG','ACTIVE','2024-01-15',8,1800),
  ('WBB','BRANCH','Wakas Bocaue','STANDALONE','HIGH_TRAFFIC_24H','AREA_BULACAN','PROV_BUL','BULACAN','ACTIVE','2024-01-15',8,2150),
  ('PCR','BRANCH','Parola Cainta','STANDALONE','RESIDENTIAL','AREA_RIZAL','PROV_STH','RIZAL','ACTIVE','2024-01-15',8,1800),
  ('SIT','BRANCH','San Isidro Taytay','STANDALONE','RESIDENTIAL','AREA_RIZAL','PROV_STH','RIZAL','ACTIVE','2024-01-15',8,1200),
  ('FMM','BRANCH','Fortune Market Marilao','STANDALONE','PUBLIC_MARKET','AREA_BULACAN','PROV_BUL','BULACAN','ACTIVE','2024-01-15',8,1800),
  ('SBL','BRANCH','San Vicente, Biñan','STANDALONE','HIGH_TRAFFIC_24H','AREA_SOUTH_LUZON','PROV_STH','LAGUNA','ACTIVE','2024-01-15',8,2300),
  ('OSM','BRANCH','Old Sta Mesa','STANDALONE','RESIDENTIAL','AREA_MANILA','W1_SOUTH','MNL','ACTIVE','2024-01-15',8,1850),
  ('LSL','BRANCH','Landayan San Pedro','STANDALONE','RESIDENTIAL','AREA_SOUTH_LUZON','PROV_STH','LAGUNA','ACTIVE','2024-01-15',8,850),
  ('ZBC','BRANCH','Zapote Bacoor','STANDALONE','RESIDENTIAL','AREA_SOUTH_LUZON','PROV_STH','LAGUNA','ACTIVE','2024-01-15',8,1550),
  ('SMM','BRANCH','Sierra Madre Mandaluyong','STANDALONE','HIGH_TRAFFIC_24H','AREA_PASIG_MANDA','W1_EAST','PSG','ACTIVE','2024-01-15',8,2250),
  ('SMB','BRANCH','Sta Maria Bulacan','STANDALONE','HIGH_TRAFFIC_24H','AREA_BULACAN','PROV_BUL','BULACAN','ACTIVE','2024-01-15',8,3700),
  ('ASP','BRANCH','Almeda Pateros','STANDALONE','RESIDENTIAL','AREA_MAKATI_TAGUIG','W1_SOUTH','TAG','ACTIVE','2024-01-15',8,1650),
  ('PSM','BRANCH','Pureza Sta Mesa','STANDALONE','HIGH_TRAFFIC_24H','AREA_MANILA','W1_SOUTH','MNL','ACTIVE','2024-01-15',8,2400),
  ('GPC','BRANCH','Grace Park Caloocan','STANDALONE','HIGH_TRAFFIC_24H','AREA_CAMANAVA','W1_NORTH','CAL','ACTIVE','2024-01-15',8,2100),
  ('TSM','BRANCH','Trabajo Sta Mesa','STANDALONE','RESIDENTIAL','AREA_MANILA','W1_SOUTH','MNL','ACTIVE','2024-01-15',8,1400),
  ('MMV','BRANCH','Malanday Valenzuela','STANDALONE','RESIDENTIAL','AREA_VALENZUELA','W2_NORTH','VAL','ACTIVE','2024-01-15',8,1250),
  ('OCR','BRANCH','Ortigas Cainta','STANDALONE','COMMERCIAL_STRIP','AREA_RIZAL','PROV_STH','RIZAL','ACTIVE','2024-01-15',8,1750),
  ('MTQ','BRANCH','Mindanao Ave','STANDALONE','RESIDENTIAL','AREA_QC','W1_NORTH','QZC','ACTIVE','2024-01-15',8,1700),
  ('MRV','BRANCH','Marulas','STANDALONE','RESIDENTIAL','AREA_VALENZUELA','W2_NORTH','VAL','ACTIVE','2024-01-15',8,1450),
  ('PCL','BRANCH','Pacita Laguna','STANDALONE','RESIDENTIAL','AREA_SOUTH_LUZON','PROV_STH','LAGUNA','ACTIVE','2024-01-15',8,1300),
  ('KCC','BRANCH','Kaybiga Caloocan','STANDALONE','HIGH_TRAFFIC_24H','AREA_CAMANAVA','W1_NORTH','CAL','ACTIVE','2024-01-15',8,2000),
  ('ARS','BRANCH','Agora San Juan','STANDALONE','PUBLIC_MARKET','AREA_PASIG_MANDA','W1_EAST','PSG','ACTIVE','2024-01-15',8,2100),
  ('PDC','BRANCH','Poblacion Cabuyao','STANDALONE','HIGH_TRAFFIC_24H','AREA_SOUTH_LUZON','PROV_STH','LAGUNA','ACTIVE','2024-01-15',8,2100),
  ('MPQ','BRANCH','Milagrosa','STANDALONE','HIGH_TRAFFIC_24H','AREA_QC','W1_NORTH','QZC','ACTIVE','2024-01-15',8,4400),
  ('RESB','BRANCH','RE South Biñan','STANDALONE','RESIDENTIAL','AREA_SOUTH_LUZON','PROV_STH','LAGUNA','RAMP_UP','2026-06-15',8,700),
  ('TUK','BRANCH','Tuktukan','STANDALONE','HIGH_TRAFFIC_24H','AREA_MAKATI_TAGUIG','W1_SOUTH','TAG','ACTIVE','2024-01-15',8,3700),
  ('NSE','BRANCH','TBC - site NSE','STANDALONE','RESIDENTIAL','AREA_MANILA','W1_SOUTH','MNL','PLANNED',NULL,8,NULL),
  ('BRT','BRANCH','TBC - site BRT','STANDALONE','RESIDENTIAL','AREA_MANILA','W1_SOUTH','MNL','PLANNED',NULL,8,NULL),
  ('BKC','BRANCH','TBC - site BKC','STANDALONE','RESIDENTIAL','AREA_MANILA','W1_SOUTH','MNL','PLANNED',NULL,8,NULL),
  ('SRC','BRANCH','TBC - site SRC','STANDALONE','RESIDENTIAL','AREA_MANILA','W1_SOUTH','MNL','PLANNED',NULL,8,NULL),
  ('SMSP','BRANCH','TBC - site SMSP','STANDALONE','RESIDENTIAL','AREA_MANILA','W1_SOUTH','MNL','PLANNED',NULL,8,NULL),
  ('SJO','BRANCH','TBC - site SJO','STANDALONE','RESIDENTIAL','AREA_MANILA','W1_SOUTH','MNL','PLANNED',NULL,8,NULL),
  ('DND','BRANCH','TBC - site DND','STANDALONE','RESIDENTIAL','AREA_MANILA','W1_SOUTH','MNL','PLANNED',NULL,8,NULL),
  ('MMP','BRANCH','TBC - site MMP','STANDALONE','RESIDENTIAL','AREA_MANILA','W1_SOUTH','MNL','PLANNED',NULL,8,NULL)
ON CONFLICT (location_code) DO NOTHING;

-- ---------------------------------------------------------------------
-- 7b. Prices — loaded here, not in part 1, because the EMC branch override
--     below requires core.location rows to already exist.             [REAL/FLAGGED]
--    unit_cost is NULL throughout: the client has not supplied cost data.
--    Waste valuation and service-level maths stay disabled until it exists.
--
--    SRP CONFLICT — NOT YET RESOLVED WITH CLIENT.
--    The Pillow Pack Sched sheet and individual store tabs disagree on SRP
--    for several items (e.g. Double Cheese Roll 15 vs 18; Cinnamon Deluxe
--    20 vs 22). It is not yet known whether this is a genuine per-branch
--    price (e.g. supermarket concessions vs standalone) or a data-entry
--    inconsistency. item_price now supports an optional location_code
--    override — see core.v_effective_price in SPEC v3 §4.3.
--
--    We seed the Pillow Pack Sched value as the NETWORK price (location_code
--    NULL, price_status CONFIRMED) for every item. Where a store-tab value
--    conflicted with it, we seed that value as a CANDIDATE BRANCH OVERRIDE
--    (price_status PENDING_REVIEW) attached to one representative
--    supermarket-concession branch (EMC - Ever Caloocan), rather than
--    silently discarding it or guessing which branches it applies to.
--
--    ACTION REQUIRED: once the client confirms whether branch-level pricing
--    is real, either (a) mark these PENDING_REVIEW rows CONFIRMED and copy
--    them to the actual branches they apply to, or (b) delete them and treat
--    the store-tab figures as historical data-entry errors.
-- ---------------------------------------------------------------------
INSERT INTO item_price (item_code, location_code, srp, unit_cost, price_status, effective_from, effective_to, note) VALUES
  ('CP001',NULL,12,NULL,'CONFIRMED','2026-07-01',NULL,'Network price from Pillow Pack Sched sheet'),
  ('CP004',NULL,12,NULL,'CONFIRMED','2026-07-01',NULL,'Network price from Pillow Pack Sched sheet'),
  ('CP006',NULL,12,NULL,'CONFIRMED','2026-07-01',NULL,'Network price from Pillow Pack Sched sheet'),
  ('CP008',NULL,12,NULL,'CONFIRMED','2026-07-01',NULL,'Network price from Pillow Pack Sched sheet'),
  ('CP025',NULL,20,NULL,'CONFIRMED','2026-07-01',NULL,'Network price from Pillow Pack Sched sheet'),
  ('CP025','EMC',22,NULL,'PENDING_REVIEW','2026-07-01',NULL,'Candidate branch override -- store-tab value 22 vs network 20. Attached to EMC as a representative concession branch pending client confirmation.'),
  ('CP028',NULL,15,NULL,'CONFIRMED','2026-07-01',NULL,'Network price from Pillow Pack Sched sheet'),
  ('CP028','EMC',18,NULL,'PENDING_REVIEW','2026-07-01',NULL,'Candidate branch override -- store-tab value 18 vs network 15. Attached to EMC as a representative concession branch pending client confirmation.'),
  ('CP034',NULL,12,NULL,'CONFIRMED','2026-07-01',NULL,'Network price from Pillow Pack Sched sheet'),
  ('CP060',NULL,30,NULL,'CONFIRMED','2026-07-01',NULL,'Network price from Pillow Pack Sched sheet'),
  ('CP060','EMC',32,NULL,'PENDING_REVIEW','2026-07-01',NULL,'Candidate branch override -- store-tab value 32 vs network 30. Attached to EMC as a representative concession branch pending client confirmation.'),
  ('CP061',NULL,25,NULL,'CONFIRMED','2026-07-01',NULL,'Network price from Pillow Pack Sched sheet'),
  ('CP061','EMC',28,NULL,'PENDING_REVIEW','2026-07-01',NULL,'Candidate branch override -- store-tab value 28 vs network 25. Attached to EMC as a representative concession branch pending client confirmation.'),
  ('CP062',NULL,30,NULL,'CONFIRMED','2026-07-01',NULL,'Network price from Pillow Pack Sched sheet'),
  ('CP062','EMC',32,NULL,'PENDING_REVIEW','2026-07-01',NULL,'Candidate branch override -- store-tab value 32 vs network 30. Attached to EMC as a representative concession branch pending client confirmation.'),
  ('CP074',NULL,25,NULL,'CONFIRMED','2026-07-01',NULL,'Network price from Pillow Pack Sched sheet'),
  ('CP074','EMC',28,NULL,'PENDING_REVIEW','2026-07-01',NULL,'Candidate branch override -- store-tab value 28 vs network 25. Attached to EMC as a representative concession branch pending client confirmation.'),
  ('CP075',NULL,25,NULL,'CONFIRMED','2026-07-01',NULL,'Network price from Pillow Pack Sched sheet'),
  ('CP075','EMC',28,NULL,'PENDING_REVIEW','2026-07-01',NULL,'Candidate branch override -- store-tab value 28 vs network 25. Attached to EMC as a representative concession branch pending client confirmation.'),
  ('CP076',NULL,15,NULL,'CONFIRMED','2026-07-01',NULL,'Network price from Pillow Pack Sched sheet'),
  ('CP077',NULL,30,NULL,'CONFIRMED','2026-07-01',NULL,'Network price from Pillow Pack Sched sheet'),
  ('CP077','EMC',32,NULL,'PENDING_REVIEW','2026-07-01',NULL,'Candidate branch override -- store-tab value 32 vs network 30. Attached to EMC as a representative concession branch pending client confirmation.'),
  ('CP088',NULL,15,NULL,'CONFIRMED','2026-07-01',NULL,'Network price from Pillow Pack Sched sheet'),
  ('CP088','EMC',18,NULL,'PENDING_REVIEW','2026-07-01',NULL,'Candidate branch override -- store-tab value 18 vs network 15. Attached to EMC as a representative concession branch pending client confirmation.'),
  ('CP095',NULL,20,NULL,'CONFIRMED','2026-07-01',NULL,'Network price from Pillow Pack Sched sheet'),
  ('CP095','EMC',22,NULL,'PENDING_REVIEW','2026-07-01',NULL,'Candidate branch override -- store-tab value 22 vs network 20. Attached to EMC as a representative concession branch pending client confirmation.'),
  ('CP096',NULL,30,NULL,'CONFIRMED','2026-07-01',NULL,'Network price from Pillow Pack Sched sheet'),
  ('CP096','EMC',32,NULL,'PENDING_REVIEW','2026-07-01',NULL,'Candidate branch override -- store-tab value 32 vs network 30. Attached to EMC as a representative concession branch pending client confirmation.'),
  ('CP097',NULL,60,NULL,'CONFIRMED','2026-07-01',NULL,'Network price from Pillow Pack Sched sheet'),
  ('CP097','EMC',62,NULL,'PENDING_REVIEW','2026-07-01',NULL,'Candidate branch override -- store-tab value 62 vs network 60. Attached to EMC as a representative concession branch pending client confirmation.'),
  ('CP099',NULL,60,NULL,'CONFIRMED','2026-07-01',NULL,'Network price from Pillow Pack Sched sheet'),
  ('CP099','EMC',62,NULL,'PENDING_REVIEW','2026-07-01',NULL,'Candidate branch override -- store-tab value 62 vs network 60. Attached to EMC as a representative concession branch pending client confirmation.'),
  ('CP102',NULL,35,NULL,'CONFIRMED','2026-07-01',NULL,'Network price from Pillow Pack Sched sheet'),
  ('CP102','EMC',38,NULL,'PENDING_REVIEW','2026-07-01',NULL,'Candidate branch override -- store-tab value 38 vs network 35. Attached to EMC as a representative concession branch pending client confirmation.'),
  ('CP103',NULL,30,NULL,'CONFIRMED','2026-07-01',NULL,'Network price from Pillow Pack Sched sheet'),
  ('CP103','EMC',32,NULL,'PENDING_REVIEW','2026-07-01',NULL,'Candidate branch override -- store-tab value 32 vs network 30. Attached to EMC as a representative concession branch pending client confirmation.'),
  ('CP104',NULL,35,NULL,'CONFIRMED','2026-07-01',NULL,'Network price from Pillow Pack Sched sheet'),
  ('CP104','EMC',38,NULL,'PENDING_REVIEW','2026-07-01',NULL,'Candidate branch override -- store-tab value 38 vs network 35. Attached to EMC as a representative concession branch pending client confirmation.'),
  ('CP105',NULL,25,NULL,'CONFIRMED','2026-07-01',NULL,'Network price from Pillow Pack Sched sheet'),
  ('CP105','EMC',28,NULL,'PENDING_REVIEW','2026-07-01',NULL,'Candidate branch override -- store-tab value 28 vs network 25. Attached to EMC as a representative concession branch pending client confirmation.'),
  ('CP106',NULL,25,NULL,'CONFIRMED','2026-07-01',NULL,'Network price from Pillow Pack Sched sheet'),
  ('CP106','EMC',28,NULL,'PENDING_REVIEW','2026-07-01',NULL,'Candidate branch override -- store-tab value 28 vs network 25. Attached to EMC as a representative concession branch pending client confirmation.'),
  ('CP107',NULL,15,NULL,'CONFIRMED','2026-07-01',NULL,'Network price from Pillow Pack Sched sheet'),
  ('CP107','EMC',18,NULL,'PENDING_REVIEW','2026-07-01',NULL,'Candidate branch override -- store-tab value 18 vs network 15. Attached to EMC as a representative concession branch pending client confirmation.'),
  ('CP109',NULL,25,NULL,'CONFIRMED','2026-07-01',NULL,'Network price from Pillow Pack Sched sheet'),
  ('CP109','EMC',28,NULL,'PENDING_REVIEW','2026-07-01',NULL,'Candidate branch override -- store-tab value 28 vs network 25. Attached to EMC as a representative concession branch pending client confirmation.'),
  ('CP110',NULL,20,NULL,'CONFIRMED','2026-07-01',NULL,'Network price from Pillow Pack Sched sheet'),
  ('CP110','EMC',22,NULL,'PENDING_REVIEW','2026-07-01',NULL,'Candidate branch override -- store-tab value 22 vs network 20. Attached to EMC as a representative concession branch pending client confirmation.'),
  ('CP112',NULL,25,NULL,'CONFIRMED','2026-07-01',NULL,'Network price from Pillow Pack Sched sheet'),
  ('CP112','EMC',28,NULL,'PENDING_REVIEW','2026-07-01',NULL,'Candidate branch override -- store-tab value 28 vs network 25. Attached to EMC as a representative concession branch pending client confirmation.'),
  ('CP113',NULL,20,NULL,'CONFIRMED','2026-07-01',NULL,'Network price from Pillow Pack Sched sheet'),
  ('CP113','EMC',22,NULL,'PENDING_REVIEW','2026-07-01',NULL,'Candidate branch override -- store-tab value 22 vs network 20. Attached to EMC as a representative concession branch pending client confirmation.'),
  ('CP116',NULL,8,NULL,'CONFIRMED','2026-07-01',NULL,'Network price from Pillow Pack Sched sheet'),
  ('CP117',NULL,8,NULL,'CONFIRMED','2026-07-01',NULL,'Network price from Pillow Pack Sched sheet'),
  ('CP118',NULL,25,NULL,'CONFIRMED','2026-07-01',NULL,'Network price from Pillow Pack Sched sheet'),
  ('CP118','EMC',28,NULL,'PENDING_REVIEW','2026-07-01',NULL,'Candidate branch override -- store-tab value 28 vs network 25. Attached to EMC as a representative concession branch pending client confirmation.'),
  ('CP120',NULL,30,NULL,'CONFIRMED','2026-07-01',NULL,'Network price from Pillow Pack Sched sheet'),
  ('CP120','EMC',32,NULL,'PENDING_REVIEW','2026-07-01',NULL,'Candidate branch override -- store-tab value 32 vs network 30. Attached to EMC as a representative concession branch pending client confirmation.'),
  ('CP121',NULL,25,NULL,'CONFIRMED','2026-07-01',NULL,'Network price from Pillow Pack Sched sheet'),
  ('CP121','EMC',28,NULL,'PENDING_REVIEW','2026-07-01',NULL,'Candidate branch override -- store-tab value 28 vs network 25. Attached to EMC as a representative concession branch pending client confirmation.')
ON CONFLICT DO NOTHING;

-- Lifecycle history must exist for every branch from day one.
INSERT INTO location_status_history (location_code, from_status, to_status, effective_from, reason_code, note, changed_by)
SELECT location_code, NULL, status, COALESCE(open_date, CURRENT_DATE), 'INITIAL_LOAD',
       'Seeded from client workbook', 1
FROM location
ON CONFLICT DO NOTHING;

-- ---------------------------------------------------------------------
-- 8. Assortment templates                                      [ASSUMED]
--    Opening a branch applies a template rather than 34 manual rows.
-- ---------------------------------------------------------------------
INSERT INTO assortment_template (template_code, label, store_format, cluster_code, is_default, is_active) VALUES
  ('TPL_CORE','Core assortment - all standalone branches','STANDALONE',NULL,TRUE,TRUE),
  ('TPL_HIGH','High traffic - full range','STANDALONE','HIGH_TRAFFIC_24H',FALSE,TRUE),
  ('TPL_CONCESSION','Supermarket concession - reduced range','CONCESSION','SUPERMARKET_CONCESSION',FALSE,TRUE),
  ('TPL_TRANSPORT','Transport hub - grab-and-go skew','STANDALONE','TRANSPORT_HUB',FALSE,TRUE)
ON CONFLICT DO NOTHING;

-- Core template: every currently orderable SKU
INSERT INTO assortment_template_item (template_code, item_code, moq_override, day_flags)
SELECT 'TPL_CORE', item_code, NULL, '{1,2,3,4,5,6,7}'
FROM item WHERE is_orderable
ON CONFLICT DO NOTHING;

INSERT INTO assortment_template_item (template_code, item_code, moq_override, day_flags)
SELECT 'TPL_HIGH', item_code, NULL, '{1,2,3,4,5,6,7}'
FROM item WHERE is_orderable
ON CONFLICT DO NOTHING;

-- Concessions drop the low-rotation loaves (MOQ far exceeds their demand)
INSERT INTO assortment_template_item (template_code, item_code, moq_override, day_flags)
SELECT 'TPL_CONCESSION', item_code, NULL, '{1,2,3,4,5,6,7}'
FROM item WHERE is_orderable AND category_code <> 'LOAF'
ON CONFLICT DO NOTHING;

-- Transport hubs: core sellers only, no muffins/loaves
INSERT INTO assortment_template_item (template_code, item_code, moq_override, day_flags)
SELECT 'TPL_TRANSPORT', item_code, NULL, '{1,2,3,4,5,6,7}'
FROM item WHERE is_orderable AND category_code NOT IN ('LOAF','CAKE_MUFFIN')
ON CONFLICT DO NOTHING;

-- ---------------------------------------------------------------------
-- 9. Apply templates to branches -> item_location_param + schedule
-- ---------------------------------------------------------------------
INSERT INTO item_location_param (item_code, location_code, is_stocked, par_qty,
                                 moq_override, display_capacity, source_template, is_overridden)
SELECT ati.item_code, l.location_code, TRUE, NULL, ati.moq_override, NULL, t.template_code, FALSE
FROM location l
JOIN assortment_template t
  ON t.template_code = CASE
       WHEN l.cluster_code = 'SUPERMARKET_CONCESSION' THEN 'TPL_CONCESSION'
       WHEN l.cluster_code = 'TRANSPORT_HUB'          THEN 'TPL_TRANSPORT'
       WHEN l.cluster_code = 'HIGH_TRAFFIC_24H'       THEN 'TPL_HIGH'
       ELSE 'TPL_CORE' END
JOIN assortment_template_item ati ON ati.template_code = t.template_code
WHERE l.location_type = 'BRANCH'
ON CONFLICT DO NOTHING;

INSERT INTO delivery_schedule (location_code, item_code, day_of_week, is_deliverable)
SELECT ilp.location_code, ilp.item_code, d.dow, TRUE
FROM item_location_param ilp
CROSS JOIN generate_series(1,7) AS d(dow)
ON CONFLICT DO NOTHING;
-- ---------------------------------------------------------------------
-- 10. Calendar 2024-2027 with PH holidays and seasons          [ASSUMED]
--     Paydays (15th / 30th) matter materially in Philippine retail.
-- ---------------------------------------------------------------------
INSERT INTO calendar (calendar_date, day_of_week, day_name, iso_week, is_payday)
SELECT d::date,
       EXTRACT(ISODOW FROM d)::smallint,
       TO_CHAR(d,'Dy'),
       EXTRACT(WEEK FROM d)::smallint,
       (EXTRACT(DAY FROM d) IN (15,30))
         OR (EXTRACT(DAY FROM d) = EXTRACT(DAY FROM (date_trunc('month',d)+interval '1 month - 1 day')))
FROM generate_series('2024-01-01'::date,'2027-12-31'::date,'1 day') d
ON CONFLICT (calendar_date) DO NOTHING;

-- Regular holidays 2026
UPDATE calendar SET is_holiday=TRUE, holiday_name=v.nm FROM (VALUES
  ('2026-01-01','New Year''s Day'),      ('2026-04-02','Maundy Thursday'),
  ('2026-04-03','Good Friday'),          ('2026-04-09','Araw ng Kagitingan'),
  ('2026-05-01','Labor Day'),            ('2026-06-12','Independence Day'),
  ('2026-08-31','National Heroes Day'),  ('2026-11-30','Bonifacio Day'),
  ('2026-12-25','Christmas Day'),        ('2026-12-30','Rizal Day')
) AS v(dt,nm) WHERE calendar_date = v.dt::date;

-- Special non-working days 2026
UPDATE calendar SET is_holiday=TRUE, holiday_name=v.nm FROM (VALUES
  ('2026-02-17','Chinese New Year'),     ('2026-04-04','Black Saturday'),
  ('2026-08-21','Ninoy Aquino Day'),     ('2026-11-01','All Saints'' Day'),
  ('2026-11-02','All Souls'' Day'),      ('2026-12-08','Immaculate Conception'),
  ('2026-12-24','Christmas Eve'),        ('2026-12-31','New Year''s Eve')
) AS v(dt,nm) WHERE calendar_date = v.dt::date;

-- Seasons that move bakery demand
UPDATE calendar SET season_flag='HOLY_WEEK'      WHERE calendar_date BETWEEN '2026-03-30' AND '2026-04-05';
UPDATE calendar SET season_flag='UNDAS'          WHERE calendar_date BETWEEN '2026-10-30' AND '2026-11-02';
UPDATE calendar SET season_flag='CHRISTMAS'      WHERE calendar_date BETWEEN '2026-12-16' AND '2026-12-31';
UPDATE calendar SET season_flag='BACK_TO_SCHOOL' WHERE calendar_date BETWEEN '2026-06-01' AND '2026-06-15';

-- ---------------------------------------------------------------------
-- 11. Reason codes                                             [ASSUMED]
--     Overrides must pick from this list, never free text — free text
--     cannot be analysed, and analysis is the point.
-- ---------------------------------------------------------------------
INSERT INTO reason_code (reason_code, category, label, requires_note, sort_order) VALUES
  ('LOCAL_EVENT','OVERRIDE','Local event / fiesta',TRUE,1),
  ('COMPETITOR_ACTIVITY','OVERRIDE','Competitor activity',FALSE,2),
  ('WEATHER','OVERRIDE','Weather / typhoon',FALSE,3),
  ('PROMO_LAUNCH','OVERRIDE','Promo or product launch',FALSE,4),
  ('STORE_CLOSURE','OVERRIDE','Store closure / reduced hours',FALSE,5),
  ('CONSISTENT_SOLD_OUT','OVERRIDE','Consistently sold out',FALSE,6),
  ('CONSISTENT_EXCESS','OVERRIDE','Consistently in excess',FALSE,7),
  ('SUPPLY_CONSTRAINT','OVERRIDE','Commissary supply constraint',FALSE,8),
  ('NEW_STORE_RAMP','OVERRIDE','New store ramp adjustment',FALSE,9),
  ('OTHER','OVERRIDE','Other',TRUE,99),
  ('UNSOLD','WASTE','Unsold at end of day',FALSE,1),
  ('DAMAGED_IN_TRANSIT','WASTE','Damaged in transit',FALSE,2),
  ('QUALITY_REJECT','WASTE','Quality reject',TRUE,3),
  ('EXPIRED','WASTE','Past shelf life',FALSE,4),
  ('STAFF_MEAL','WASTE','Staff meal',FALSE,5),
  ('SAMPLING','WASTE','Sampling / tasting',FALSE,6),
  ('DONATION','WASTE','Donation',FALSE,7),
  ('SHORT_DELIVERY','WASTE','Short delivery',TRUE,8),
  ('COUNT_ERROR','WASTE','Count error',TRUE,9),
  ('CORRECTION','ADJUSTMENT','Ledger correction',TRUE,1),
  ('INITIAL_LOAD','ADJUSTMENT','Initial data load',FALSE,2),
  ('CYCLE_COUNT','ADJUSTMENT','Cycle count adjustment',TRUE,3)
ON CONFLICT DO NOTHING;

-- ---------------------------------------------------------------------
-- 12. Source systems and mapping profiles                      [ASSUMED]
--     Null tokens are critical: the client's files mix '', '-', '- ' and 0.
--     Blank must never become zero. See SPEC 4.5.
-- ---------------------------------------------------------------------
INSERT INTO source_system (source_code, label, system_type, is_active) VALUES
  ('DR_SYSTEM','Delivery Receipt system','ERP',TRUE),
  ('POS_MAIN','Branch POS','POS',TRUE),
  ('MANUAL_UPLOAD','Manual file upload','FILE',TRUE),
  ('GRABFOOD','GrabFood aggregator','AGGREGATOR',TRUE),
  ('FOODPANDA','Foodpanda aggregator','AGGREGATOR',TRUE)
ON CONFLICT DO NOTHING;

INSERT INTO mapping_profile (source_code, profile_name, file_type, column_map,
                             date_format, header_row, sheet_name, transform_rules) VALUES
  ('MANUAL_UPLOAD','Legacy workbook - Deliveries','DELIVERIES',
   '{"Store Code":"location_code","Item Code":"item_code","Date":"business_date","Deliveries":"deliveries_qty"}',
   'DD/MM/YYYY',1,NULL,
   '{"trim":true,"null_tokens":["","-","N/A","#N/A","null"],"reject_negative":true}'),
  ('MANUAL_UPLOAD','Legacy workbook - Offtake','SALES',
   '{"Store Code":"location_code","Item Code":"item_code","Date":"business_date","Offtake":"sales_qty"}',
   'DD/MM/YYYY',1,NULL,
   '{"trim":true,"null_tokens":["","-","N/A","#N/A","null"],"reject_negative":true}'),
  ('MANUAL_UPLOAD','Legacy workbook - Raw EI','END_INVENTORY',
   '{"Store Code":"location_code","Item Code":"item_code","Date":"business_date","EI":"end_inventory_qty"}',
   'DD/MM/YYYY',1,'Raw EI',
   '{"trim":true,"null_tokens":["","-","N/A","#N/A"],"blank_means_not_counted":true}')
ON CONFLICT DO NOTHING;
-- ---------------------------------------------------------------------
-- 13. Roles                                                    [ASSUMED]
--     Mapped to real Cocopan positions (SPEC 7.1).
-- ---------------------------------------------------------------------
INSERT INTO role (role_code, label, description, is_system) VALUES
  ('SYS_ADMIN','System Administrator','IT / systems configuration',TRUE),
  ('DEMAND_PLANNER','Demand Planner','Owns order runs, forecast and parameters',TRUE),
  ('CX_SPECIALIST','CX Specialist','Reviews and recommends order adjustments',FALSE),
  ('OPS_MANAGER','Operations Manager','Final order adjustment for assigned branches',FALSE),
  ('AREA_HEAD','Area Head','Oversight across several Operations Managers',FALSE),
  ('STORE_HEAD','Store Head','Branch counts, receiving, waste, review',FALSE),
  ('STORE_TEAM','Store Team Member','Count and waste capture only',FALSE),
  ('PPIC_PLANNER','PPIC Planner','Receives and confirms production requirement',FALSE),
  ('COMMISSARY_SUPERVISOR','Commissary Supervisor','Production receipts and dispatch',FALSE),
  ('FINANCE_ANALYST','Finance Analyst','Cost, waste valuation, analytics',FALSE),
  ('EXECUTIVE','Executive','Read-only dashboards and scorecards',FALSE),
  ('INTEGRATION','Integration Service','API ingestion only',TRUE)
ON CONFLICT DO NOTHING;

-- ---------------------------------------------------------------------
-- 14. Permissions
-- ---------------------------------------------------------------------
INSERT INTO permission (permission_code, resource, action, label, is_destructive) VALUES
  ('item.read','item','read','View items',FALSE),
  ('item.create','item','create','Create items',FALSE),
  ('item.update','item','update','Edit items',FALSE),
  ('item.delete','item','delete','Delist items',TRUE),
  ('item.price.update','item','price_update','Change prices and costs',FALSE),
  ('location.read','location','read','View branches',FALSE),
  ('location.create','location','create','Create branches',FALSE),
  ('location.update','location','update','Edit branches',FALSE),
  ('location.status_change','location','status_change','Change branch lifecycle status',TRUE),
  ('location.assign_om','location','assign_om','Assign Operations Manager',FALSE),
  ('location.closure.manage','location','closure_manage','Manage branch closures',FALSE),
  ('assortment.manage','assortment','manage','Manage branch assortment',FALSE),
  ('refdata.manage','refdata','manage','Manage reference data',FALSE),
  ('param.read','param','read','View parameters',FALSE),
  ('param.update','param','update','Change forecast and ladder parameters',TRUE),
  ('order.read','order','read','View orders',FALSE),
  ('order.generate','order','generate','Generate order runs',FALSE),
  ('order.adjust_cx','order','adjust_cx','Enter CX recommendations',FALSE),
  ('order.adjust_om','order','adjust_om','Enter OM adjustments',FALSE),
  ('order.lock','order','lock','Lock an order run',TRUE),
  ('order.submit_ppic','order','submit_ppic','Submit to PPIC',TRUE),
  ('order.confirm_production','order','confirm_production','Confirm production requirement',FALSE),
  ('count.submit','count','submit','Submit physical counts',FALSE),
  ('count.approve','count','approve','Approve count variances',FALSE),
  ('receiving.confirm','receiving','confirm','Confirm delivery receipt',FALSE),
  ('waste.record','waste','record','Record waste',FALSE),
  ('movement.adjust','movement','adjust','Manual stock adjustment',TRUE),
  ('accuracy.read','accuracy','read','View accuracy and bias',FALSE),
  ('user.manage','user','manage','Manage users and scopes',TRUE),
  ('role.manage','role','manage','Manage roles and permissions',TRUE),
  ('audit.read','audit','read','View audit trail',FALSE),
  ('integration.manage','integration','manage','Manage integrations',TRUE),
  ('export.data','export','data','Export data',FALSE)
ON CONFLICT DO NOTHING;

-- ---------------------------------------------------------------------
-- 15. Role -> permission grants (SPEC 7.3)
-- ---------------------------------------------------------------------
INSERT INTO role_permission (role_code, permission_code)
SELECT 'SYS_ADMIN', permission_code FROM permission
ON CONFLICT DO NOTHING;

INSERT INTO role_permission (role_code, permission_code) VALUES
  ('DEMAND_PLANNER','item.read'),('DEMAND_PLANNER','item.create'),('DEMAND_PLANNER','item.update'),
  ('DEMAND_PLANNER','location.read'),('DEMAND_PLANNER','location.create'),('DEMAND_PLANNER','location.update'),
  ('DEMAND_PLANNER','location.status_change'),('DEMAND_PLANNER','location.assign_om'),
  ('DEMAND_PLANNER','location.closure.manage'),('DEMAND_PLANNER','assortment.manage'),
  ('DEMAND_PLANNER','refdata.manage'),('DEMAND_PLANNER','param.read'),('DEMAND_PLANNER','param.update'),
  ('DEMAND_PLANNER','order.read'),('DEMAND_PLANNER','order.generate'),('DEMAND_PLANNER','order.adjust_cx'),
  ('DEMAND_PLANNER','order.adjust_om'),('DEMAND_PLANNER','order.lock'),('DEMAND_PLANNER','order.submit_ppic'),
  ('DEMAND_PLANNER','movement.adjust'),('DEMAND_PLANNER','accuracy.read'),('DEMAND_PLANNER','audit.read'),
  ('DEMAND_PLANNER','export.data'),

  ('CX_SPECIALIST','item.read'),('CX_SPECIALIST','location.read'),('CX_SPECIALIST','param.read'),
  ('CX_SPECIALIST','order.read'),('CX_SPECIALIST','order.adjust_cx'),('CX_SPECIALIST','accuracy.read'),
  ('CX_SPECIALIST','export.data'),

  ('OPS_MANAGER','item.read'),('OPS_MANAGER','location.read'),('OPS_MANAGER','location.closure.manage'),
  ('OPS_MANAGER','assortment.manage'),('OPS_MANAGER','param.read'),('OPS_MANAGER','order.read'),
  ('OPS_MANAGER','order.adjust_om'),('OPS_MANAGER','count.submit'),('OPS_MANAGER','count.approve'),
  ('OPS_MANAGER','receiving.confirm'),('OPS_MANAGER','waste.record'),('OPS_MANAGER','movement.adjust'),
  ('OPS_MANAGER','accuracy.read'),('OPS_MANAGER','export.data'),

  ('AREA_HEAD','item.read'),('AREA_HEAD','location.read'),('AREA_HEAD','location.assign_om'),
  ('AREA_HEAD','location.closure.manage'),('AREA_HEAD','param.read'),('AREA_HEAD','order.read'),
  ('AREA_HEAD','order.adjust_om'),('AREA_HEAD','count.approve'),('AREA_HEAD','accuracy.read'),
  ('AREA_HEAD','export.data'),

  ('STORE_HEAD','item.read'),('STORE_HEAD','location.read'),('STORE_HEAD','order.read'),
  ('STORE_HEAD','count.submit'),('STORE_HEAD','count.approve'),('STORE_HEAD','receiving.confirm'),
  ('STORE_HEAD','waste.record'),('STORE_HEAD','accuracy.read'),

  ('STORE_TEAM','item.read'),('STORE_TEAM','location.read'),('STORE_TEAM','count.submit'),
  ('STORE_TEAM','receiving.confirm'),('STORE_TEAM','waste.record'),

  ('PPIC_PLANNER','item.read'),('PPIC_PLANNER','location.read'),('PPIC_PLANNER','order.read'),
  ('PPIC_PLANNER','order.confirm_production'),('PPIC_PLANNER','accuracy.read'),('PPIC_PLANNER','export.data'),

  ('COMMISSARY_SUPERVISOR','item.read'),('COMMISSARY_SUPERVISOR','location.read'),
  ('COMMISSARY_SUPERVISOR','order.read'),('COMMISSARY_SUPERVISOR','receiving.confirm'),
  ('COMMISSARY_SUPERVISOR','movement.adjust'),

  ('FINANCE_ANALYST','item.read'),('FINANCE_ANALYST','item.price.update'),('FINANCE_ANALYST','location.read'),
  ('FINANCE_ANALYST','param.read'),('FINANCE_ANALYST','order.read'),('FINANCE_ANALYST','accuracy.read'),
  ('FINANCE_ANALYST','audit.read'),('FINANCE_ANALYST','export.data'),

  ('EXECUTIVE','item.read'),('EXECUTIVE','location.read'),('EXECUTIVE','order.read'),
  ('EXECUTIVE','accuracy.read'),

  ('INTEGRATION','item.read'),('INTEGRATION','location.read')
ON CONFLICT DO NOTHING;
-- ---------------------------------------------------------------------
-- 16. Users                                                    [ASSUMED]
--     Placeholder accounts modelled on real Cocopan positions.
--     Replace emails and set real credentials before any deployment.
--     password_hash is NULL: SSO-first. Do NOT ship a default password.
-- ---------------------------------------------------------------------
INSERT INTO app_user (user_id, email, full_name, role_hint, is_active, is_service) VALUES
  (1,'system@cocopan.ph','System','SYS_ADMIN',TRUE,TRUE)
ON CONFLICT DO NOTHING;

INSERT INTO app_user (email, full_name, is_active, is_service) VALUES
  ('it.admin@cocopan.ph','IT Administrator',TRUE,FALSE),
  ('demand.planner@cocopan.ph','Demand Planning Analyst',TRUE,FALSE),
  ('cx.lead@cocopan.ph','CX Lead',TRUE,FALSE),
  ('om.north@cocopan.ph','Operations Manager - North',TRUE,FALSE),
  ('om.south@cocopan.ph','Operations Manager - South',TRUE,FALSE),
  ('om.east@cocopan.ph','Operations Manager - East',TRUE,FALSE),
  ('om.central@cocopan.ph','Operations Manager - Central',TRUE,FALSE),
  ('om.provincial@cocopan.ph','Operations Manager - Provincial',TRUE,FALSE),
  ('area.head@cocopan.ph','Area Head - NCR',TRUE,FALSE),
  ('ppic@cocopan.ph','PPIC Planner',TRUE,FALSE),
  ('commissary.sup@cocopan.ph','Commissary Supervisor',TRUE,FALSE),
  ('finance@cocopan.ph','Finance Analyst',TRUE,FALSE),
  ('exec@cocopan.ph','Executive',TRUE,FALSE),
  ('svc.pos@cocopan.ph','POS Integration Service',TRUE,TRUE)
ON CONFLICT DO NOTHING;

INSERT INTO user_role (user_id, role_code, granted_by)
SELECT u.user_id, v.rc, 1 FROM app_user u JOIN (VALUES
  ('it.admin@cocopan.ph','SYS_ADMIN'),
  ('demand.planner@cocopan.ph','DEMAND_PLANNER'),
  ('cx.lead@cocopan.ph','CX_SPECIALIST'),
  ('om.north@cocopan.ph','OPS_MANAGER'),
  ('om.south@cocopan.ph','OPS_MANAGER'),
  ('om.east@cocopan.ph','OPS_MANAGER'),
  ('om.central@cocopan.ph','OPS_MANAGER'),
  ('om.provincial@cocopan.ph','OPS_MANAGER'),
  ('area.head@cocopan.ph','AREA_HEAD'),
  ('ppic@cocopan.ph','PPIC_PLANNER'),
  ('commissary.sup@cocopan.ph','COMMISSARY_SUPERVISOR'),
  ('finance@cocopan.ph','FINANCE_ANALYST'),
  ('exec@cocopan.ph','EXECUTIVE'),
  ('svc.pos@cocopan.ph','INTEGRATION')
) AS v(em,rc) ON u.email = v.em
ON CONFLICT DO NOTHING;

-- Branch scope. Network-wide roles get scope_type ALL; OMs get areas.
INSERT INTO user_scope (user_id, scope_type, scope_value)
SELECT u.user_id, v.st, v.sv FROM app_user u JOIN (VALUES
  ('it.admin@cocopan.ph','ALL','*'),
  ('demand.planner@cocopan.ph','ALL','*'),
  ('cx.lead@cocopan.ph','ALL','*'),
  ('ppic@cocopan.ph','ALL','*'),
  ('finance@cocopan.ph','ALL','*'),
  ('exec@cocopan.ph','ALL','*'),
  ('svc.pos@cocopan.ph','ALL','*'),
  ('commissary.sup@cocopan.ph','LOCATION','CMSY-01'),
  ('area.head@cocopan.ph','AREA','AREA_QC'),
  ('area.head@cocopan.ph','AREA','AREA_MANILA'),
  ('area.head@cocopan.ph','AREA','AREA_CAMANAVA'),
  ('om.north@cocopan.ph','AREA','AREA_CAMANAVA'),
  ('om.north@cocopan.ph','AREA','AREA_VALENZUELA'),
  ('om.south@cocopan.ph','AREA','AREA_SOUTH_NCR'),
  ('om.south@cocopan.ph','AREA','AREA_MAKATI_TAGUIG'),
  ('om.east@cocopan.ph','AREA','AREA_PASIG_MANDA'),
  ('om.east@cocopan.ph','AREA','AREA_RIZAL'),
  ('om.central@cocopan.ph','AREA','AREA_MANILA'),
  ('om.central@cocopan.ph','AREA','AREA_QC'),
  ('om.provincial@cocopan.ph','AREA','AREA_BULACAN'),
  ('om.provincial@cocopan.ph','AREA','AREA_SOUTH_LUZON')
) AS v(em,st,sv) ON u.email = v.em
ON CONFLICT DO NOTHING;

-- location.om_user_id grants scope automatically (SPEC 7.2) — wire OMs to branches
UPDATE location l SET om_user_id = u.user_id
FROM app_user u, user_scope us
WHERE us.user_id = u.user_id
  AND us.scope_type = 'AREA'
  AND us.scope_value = l.area_code
  AND u.email LIKE 'om.%'
  AND l.location_type = 'BRANCH';

-- ---------------------------------------------------------------------
-- 17. Parameter set — reproduces the client's current logic       [REAL]
--     Values from the client's email and the workbook Parameters sheet:
--       safety stock 5% · MOQ trigger 6 pcs · tier boundary at 20 units
--       cutoff 7:00 PM · PPIC submission 8:00 PM
--     topup_pct_low / topup_pct_high are 0 pending calibration (SPEC 14 AC-1).
--     carryover_enabled = FALSE so AC-1 can reproduce the workbook exactly.
-- ---------------------------------------------------------------------
INSERT INTO param_set (name, scope_level, scope_key, effective_from,
  ref_week_flags, safety_stock_pct, topup_threshold_units,
  topup_pct_low, topup_pct_high, reduction_pct,
  moq_trigger_enabled, moq_trigger_qty, moq_demand_multiple,
  min_observations, carryover_enabled, cutoff_time, ppic_submit_time, created_by)
VALUES (
  'Client Baseline (as-is)','GLOBAL',NULL,'2026-01-01',
  '{"1":{"mon":true,"tue":true,"wed":true,"thu":true,"fri":true,"sat":true,"sun":true},
    "2":{"mon":true,"tue":true,"wed":true,"thu":true,"fri":true,"sat":true,"sun":true},
    "3":{"mon":false,"tue":false,"wed":false,"thu":false,"fri":false,"sat":false,"sun":false},
    "4":{"mon":false,"tue":false,"wed":false,"thu":false,"fri":false,"sat":false,"sun":false}}',
  0.0500, 20, 0.0000, 0.0000, 0.0000,
  TRUE, 6, 3.0, 2, FALSE, '19:00', '20:00', 1
),
(
  'Optimised v1 (carryover enabled)','GLOBAL',NULL,'2099-01-01',
  '{"1":{"mon":true,"tue":true,"wed":true,"thu":true,"fri":true,"sat":true,"sun":true},
    "2":{"mon":true,"tue":true,"wed":true,"thu":true,"fri":true,"sat":true,"sun":true},
    "3":{"mon":true,"tue":true,"wed":true,"thu":true,"fri":true,"sat":true,"sun":true},
    "4":{"mon":true,"tue":true,"wed":true,"thu":true,"fri":true,"sat":true,"sun":true}}',
  0.0300, 20, 0.0000, 0.0000, 0.0000,
  TRUE, 6, 3.0, 2, TRUE, '19:00', '20:00', 1
)
ON CONFLICT DO NOTHING;

COMMIT;

-- =====================================================================
--  VERIFICATION
-- =====================================================================
SELECT 'items'          AS entity, COUNT(*) FROM item
UNION ALL SELECT 'items orderable',   COUNT(*) FROM item WHERE is_orderable
UNION ALL SELECT 'items multi-day',   COUNT(*) FROM item WHERE replen_policy='MULTI_DAY'
UNION ALL SELECT 'branches',          COUNT(*) FROM location WHERE location_type='BRANCH'
UNION ALL SELECT 'branches active',   COUNT(*) FROM location WHERE is_active
UNION ALL SELECT 'branches orderable',COUNT(*) FROM location WHERE is_orderable
UNION ALL SELECT 'assortment rows',   COUNT(*) FROM item_location_param
UNION ALL SELECT 'schedule rows',     COUNT(*) FROM delivery_schedule
UNION ALL SELECT 'calendar days',     COUNT(*) FROM calendar
UNION ALL SELECT 'roles',             COUNT(*) FROM role
UNION ALL SELECT 'permissions',       COUNT(*) FROM permission
UNION ALL SELECT 'role grants',       COUNT(*) FROM role_permission
UNION ALL SELECT 'users',             COUNT(*) FROM app_user
UNION ALL SELECT 'param sets',        COUNT(*) FROM param_set;

-- Branches by status — expect ACTIVE 102, PLANNED 8, PRE_OPENING 7, RAMP_UP 4
SELECT status, COUNT(*) FROM location WHERE location_type='BRANCH' GROUP BY status ORDER BY 2 DESC;

-- Sanity check: MOQ that exceeds ~3 days of demand is a structural waste source.
-- Chicken Asado Bun (MOQ 10) and Choco Roll (MOQ 12) should surface here once
-- sales history is loaded. See SPEC 9 Step 4.
SELECT item_code, display_name, moq, shelf_life_days, replen_policy
FROM item WHERE moq > 0 ORDER BY moq DESC, item_code;

-- UNRESOLVED: SRP conflicts flagged for client review (see part 2, section 7b).
-- These will not affect any order calculation until confirmed -- v_effective_price
-- only prefers a branch row over the network row for the exact branch it is on.
SELECT item_code, location_code, srp, price_status, note
FROM item_price WHERE price_status = 'PENDING_REVIEW'
ORDER BY item_code;
