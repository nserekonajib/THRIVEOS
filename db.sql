-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Create users table first (no business dependencies)
CREATE TABLE public.users (
  id uuid NOT NULL DEFAULT uuid_generate_v4(),
  email character varying NOT NULL UNIQUE,
  password_hash text NOT NULL,
  first_name character varying,
  last_name character varying,
  phone_number character varying,
  email_verified boolean DEFAULT false,
  otp_secret text,
  otp_expiry timestamp with time zone,
  reset_token text,
  reset_token_expiry timestamp with time zone,
  created_at timestamp with time zone DEFAULT now(),
  updated_at timestamp with time zone DEFAULT now(),
  last_login timestamp with time zone,
  login_count integer DEFAULT 0,
  verified_at timestamp with time zone,
  role character varying DEFAULT 'user'::character varying,
  is_admin boolean DEFAULT false,
  role_id uuid,
  is_active boolean DEFAULT true,
  department character varying,
  position character varying,
  hire_date date,
  reports_to uuid,
  two_factor_enabled boolean DEFAULT false,
  biometric_enabled boolean DEFAULT false,
  business_id uuid,
  CONSTRAINT users_pkey PRIMARY KEY (id),
  CONSTRAINT users_reports_to_fkey FOREIGN KEY (reports_to) REFERENCES public.users(id)
);

-- Create user_roles table
CREATE TABLE public.user_roles (
  id uuid NOT NULL DEFAULT uuid_generate_v4(),
  name character varying NOT NULL UNIQUE,
  description text,
  permissions jsonb DEFAULT '{}'::jsonb,
  is_default boolean DEFAULT false,
  is_admin boolean DEFAULT false,
  can_manage_users boolean DEFAULT false,
  can_manage_roles boolean DEFAULT false,
  can_view_analytics boolean DEFAULT false,
  can_manage_settings boolean DEFAULT false,
  created_at timestamp with time zone DEFAULT now(),
  updated_at timestamp with time zone DEFAULT now(),
  CONSTRAINT user_roles_pkey PRIMARY KEY (id)
);

-- Add foreign key constraint to users after user_roles exists
ALTER TABLE public.users 
ADD CONSTRAINT users_role_id_fkey FOREIGN KEY (role_id) REFERENCES public.user_roles(id);

-- Create businesses table (depends on users)
CREATE TABLE public.businesses (
  id uuid NOT NULL DEFAULT uuid_generate_v4(),
  user_id uuid NOT NULL,
  business_name character varying NOT NULL,
  business_email character varying,
  business_phone character varying,
  address text,
  city character varying,
  country character varying,
  logo_url text,
  cloudinary_public_id text,
  created_at timestamp with time zone DEFAULT now(),
  updated_at timestamp with time zone DEFAULT now(),
  CONSTRAINT businesses_pkey PRIMARY KEY (id),
  CONSTRAINT fk_businesses_user_id FOREIGN KEY (user_id) REFERENCES public.users(id)
);

-- Add foreign key constraints to users that reference businesses
ALTER TABLE public.users 
ADD CONSTRAINT fk_users_business_id FOREIGN KEY (business_id) REFERENCES public.businesses(id);

-- Create business_settings (depends on businesses)
CREATE TABLE public.business_settings (
  id uuid NOT NULL DEFAULT uuid_generate_v4(),
  business_id uuid NOT NULL UNIQUE,
  pesapal_consumer_key text,
  pesapal_consumer_secret text,
  pesapal_ipn_url text,
  currency character varying DEFAULT 'UGX'::character varying,
  tax_rate numeric DEFAULT 18.00,
  receipt_footer text,
  timezone character varying DEFAULT 'Africa/Nairobi'::character varying,
  email_smtp_server text,
  email_smtp_port integer DEFAULT 587,
  email_smtp_username text,
  email_smtp_password text,
  email_from_address text,
  sms_api_key text,
  sms_api_secret text,
  sms_sender_id text,
  printer_ip character varying,
  printer_port integer DEFAULT 9100,
  session_timeout integer DEFAULT 30,
  require_pin_for_refund boolean DEFAULT true,
  require_manager_approval_amount numeric DEFAULT 10000.00,
  created_at timestamp with time zone DEFAULT now(),
  updated_at timestamp with time zone DEFAULT now(),
  CONSTRAINT business_settings_pkey PRIMARY KEY (id),
  CONSTRAINT business_settings_business_id_fkey FOREIGN KEY (business_id) REFERENCES public.businesses(id)
);

-- Create suppliers (depends on businesses and users)
CREATE TABLE public.suppliers (
  id uuid NOT NULL DEFAULT uuid_generate_v4(),
  business_id uuid NOT NULL,
  name character varying NOT NULL,
  contact character varying,
  phone character varying,
  email character varying,
  address text,
  created_by uuid,
  created_at timestamp with time zone DEFAULT now(),
  updated_at timestamp with time zone DEFAULT now(),
  CONSTRAINT suppliers_pkey PRIMARY KEY (id),
  CONSTRAINT suppliers_business_id_fkey FOREIGN KEY (business_id) REFERENCES public.businesses(id),
  CONSTRAINT suppliers_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.users(id)
);

-- Create categories (depends on businesses and users)
CREATE TABLE public.categories (
  id uuid NOT NULL DEFAULT uuid_generate_v4(),
  business_id uuid NOT NULL,
  name character varying NOT NULL,
  description text,
  created_by uuid,
  created_at timestamp with time zone DEFAULT now(),
  updated_at timestamp with time zone DEFAULT now(),
  is_active boolean DEFAULT true,
  CONSTRAINT categories_pkey PRIMARY KEY (id),
  CONSTRAINT categories_business_id_fkey FOREIGN KEY (business_id) REFERENCES public.businesses(id),
  CONSTRAINT categories_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.users(id)
);

-- Create products (depends on businesses, categories, suppliers, and users)
CREATE TABLE public.products (
  id uuid NOT NULL DEFAULT uuid_generate_v4(),
  business_id uuid NOT NULL,
  name character varying NOT NULL,
  sku character varying,
  barcode character varying,
  category_id uuid,
  supplier_id uuid,
  cost_price numeric DEFAULT 0,
  selling_price numeric NOT NULL,
  tax_rate numeric DEFAULT 0,
  unit character varying,
  description text,
  image_url text,
  reorder_level integer DEFAULT 0,
  is_active boolean DEFAULT true,
  created_by uuid,
  created_at timestamp with time zone DEFAULT now(),
  updated_at timestamp with time zone DEFAULT now(),
  cloudinary_public_id text,
  CONSTRAINT products_pkey PRIMARY KEY (id),
  CONSTRAINT products_business_id_fkey FOREIGN KEY (business_id) REFERENCES public.businesses(id),
  CONSTRAINT products_category_id_fkey FOREIGN KEY (category_id) REFERENCES public.categories(id),
  CONSTRAINT products_supplier_id_fkey FOREIGN KEY (supplier_id) REFERENCES public.suppliers(id),
  CONSTRAINT products_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.users(id)
);

-- Create product_attributes (depends on businesses)
CREATE TABLE public.product_attributes (
  id uuid NOT NULL DEFAULT uuid_generate_v4(),
  business_id uuid NOT NULL,
  name character varying NOT NULL,
  display_name character varying,
  created_at timestamp with time zone DEFAULT now(),
  CONSTRAINT product_attributes_pkey PRIMARY KEY (id),
  CONSTRAINT product_attributes_business_id_fkey FOREIGN KEY (business_id) REFERENCES public.businesses(id)
);

-- Create product_attribute_values (depends on product_attributes)
CREATE TABLE public.product_attribute_values (
  id uuid NOT NULL DEFAULT uuid_generate_v4(),
  attribute_id uuid NOT NULL,
  value character varying NOT NULL,
  display_order integer DEFAULT 0,
  created_at timestamp with time zone DEFAULT now(),
  CONSTRAINT product_attribute_values_pkey PRIMARY KEY (id),
  CONSTRAINT product_attribute_values_attribute_id_fkey FOREIGN KEY (attribute_id) REFERENCES public.product_attributes(id)
);

-- Create product_lots (depends on products and users)
CREATE TABLE public.product_lots (
  id uuid NOT NULL DEFAULT uuid_generate_v4(),
  product_id uuid NOT NULL,
  lot_number character varying,
  expiry_date date,
  quantity integer NOT NULL DEFAULT 0,
  cost_price numeric,
  created_by uuid,
  created_at timestamp with time zone DEFAULT now(),
  updated_at timestamp with time zone DEFAULT now(),
  CONSTRAINT product_lots_pkey PRIMARY KEY (id),
  CONSTRAINT product_lots_product_id_fkey FOREIGN KEY (product_id) REFERENCES public.products(id),
  CONSTRAINT product_lots_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.users(id)
);

-- Create sales (depends on businesses and users)
CREATE TABLE public.sales (
  id uuid NOT NULL DEFAULT uuid_generate_v4(),
  business_id uuid NOT NULL,
  invoice_number character varying NOT NULL,
  customer_name character varying,
  customer_phone character varying,
  customer_email character varying,
  subtotal numeric NOT NULL DEFAULT 0,
  tax_amount numeric NOT NULL DEFAULT 0,
  discount_amount numeric NOT NULL DEFAULT 0,
  total_amount numeric NOT NULL DEFAULT 0,
  payment_method character varying NOT NULL,
  payment_status character varying NOT NULL DEFAULT 'pending'::character varying,
  pesapal_order_id character varying,
  notes text,
  sold_by uuid,
  created_at timestamp with time zone DEFAULT now(),
  updated_at timestamp with time zone DEFAULT now(),
  refund_id uuid,
  refund_amount numeric DEFAULT 0,
  CONSTRAINT sales_pkey PRIMARY KEY (id),
  CONSTRAINT sales_business_id_fkey FOREIGN KEY (business_id) REFERENCES public.businesses(id),
  CONSTRAINT sales_sold_by_fkey FOREIGN KEY (sold_by) REFERENCES public.users(id)
);

-- Create sale_items (depends on sales and products)
CREATE TABLE public.sale_items (
  id uuid NOT NULL DEFAULT uuid_generate_v4(),
  sale_id uuid NOT NULL,
  product_id uuid NOT NULL,
  product_name character varying NOT NULL,
  sku character varying,
  quantity integer NOT NULL DEFAULT 1,
  unit_price numeric NOT NULL DEFAULT 0,
  tax_rate numeric NOT NULL DEFAULT 0,
  total_price numeric NOT NULL DEFAULT 0,
  created_at timestamp with time zone DEFAULT now(),
  CONSTRAINT sale_items_pkey PRIMARY KEY (id),
  CONSTRAINT sale_items_sale_id_fkey FOREIGN KEY (sale_id) REFERENCES public.sales(id),
  CONSTRAINT sale_items_product_id_fkey FOREIGN KEY (product_id) REFERENCES public.products(id)
);

-- Create payment_sessions (depends on sales)
CREATE TABLE public.payment_sessions (
  id uuid NOT NULL DEFAULT uuid_generate_v4(),
  sale_id uuid NOT NULL,
  order_tracking_id character varying NOT NULL UNIQUE,
  reference_id character varying NOT NULL,
  amount numeric NOT NULL,
  created_at timestamp with time zone DEFAULT now(),
  CONSTRAINT payment_sessions_pkey PRIMARY KEY (id),
  CONSTRAINT payment_sessions_sale_id_fkey FOREIGN KEY (sale_id) REFERENCES public.sales(id)
);

-- Create refunds (depends on businesses, sales, and users)
CREATE TABLE public.refunds (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  business_id uuid NOT NULL,
  sale_id uuid NOT NULL,
  refund_amount numeric NOT NULL,
  refund_reason text,
  refunded_by uuid,
  payment_method character varying NOT NULL,
  status character varying DEFAULT 'pending'::character varying,
  notes text,
  created_at timestamp with time zone DEFAULT now(),
  updated_at timestamp with time zone DEFAULT now(),
  CONSTRAINT refunds_pkey PRIMARY KEY (id),
  CONSTRAINT refunds_business_id_fkey FOREIGN KEY (business_id) REFERENCES public.businesses(id),
  CONSTRAINT refunds_sale_id_fkey FOREIGN KEY (sale_id) REFERENCES public.sales(id),
  CONSTRAINT refunds_refunded_by_fkey FOREIGN KEY (refunded_by) REFERENCES public.users(id)
);

-- Create refund_items (depends on refunds and products)
CREATE TABLE public.refund_items (
  id uuid NOT NULL DEFAULT uuid_generate_v4(),
  refund_id uuid NOT NULL,
  product_id uuid NOT NULL,
  quantity integer NOT NULL DEFAULT 1,
  unit_price numeric NOT NULL DEFAULT 0,
  total_price numeric NOT NULL DEFAULT 0,
  reason text,
  created_at timestamp with time zone DEFAULT now(),
  CONSTRAINT refund_items_pkey PRIMARY KEY (id),
  CONSTRAINT refund_items_refund_id_fkey FOREIGN KEY (refund_id) REFERENCES public.refunds(id),
  CONSTRAINT refund_items_product_id_fkey FOREIGN KEY (product_id) REFERENCES public.products(id)
);

-- Create inventory_movements (depends on products, product_lots, and users)
CREATE TABLE public.inventory_movements (
  id uuid NOT NULL DEFAULT uuid_generate_v4(),
  product_id uuid NOT NULL,
  lot_id uuid,
  movement_type character varying NOT NULL CHECK (movement_type::text = ANY (ARRAY['IN'::character varying, 'OUT'::character varying, 'ADJUST'::character varying, 'TRANSFER'::character varying]::text[])),
  quantity integer NOT NULL,
  reference text,
  notes text,
  created_by uuid,
  created_at timestamp with time zone DEFAULT now(),
  updated_at timestamp with time zone DEFAULT now(),
  CONSTRAINT inventory_movements_pkey PRIMARY KEY (id),
  CONSTRAINT inventory_movements_product_id_fkey FOREIGN KEY (product_id) REFERENCES public.products(id),
  CONSTRAINT inventory_movements_lot_id_fkey FOREIGN KEY (lot_id) REFERENCES public.product_lots(id),
  CONSTRAINT inventory_movements_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.users(id)
);

-- Create expenses (depends on businesses)
CREATE TABLE public.expenses (
  id uuid NOT NULL DEFAULT uuid_generate_v4(),
  business_id uuid NOT NULL,
  expense_date date NOT NULL,
  vendor character varying,
  description text,
  category character varying NOT NULL,
  amount numeric NOT NULL,
  payment_method character varying NOT NULL,
  receipt_url text,
  status character varying DEFAULT 'pending'::character varying,
  notes text,
  created_by uuid,
  created_at timestamp with time zone DEFAULT now(),
  updated_at timestamp with time zone DEFAULT now(),
  CONSTRAINT expenses_pkey PRIMARY KEY (id),
  CONSTRAINT expenses_business_id_fkey FOREIGN KEY (business_id) REFERENCES public.businesses(id),
  CONSTRAINT expenses_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.users(id)
);

-- Create audit_logs (depends on businesses and users)
CREATE TABLE public.audit_logs (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  business_id uuid NOT NULL,
  user_id uuid NOT NULL,
  action character varying NOT NULL,
  details jsonb,
  ip_address character varying,
  user_agent text,
  created_at timestamp with time zone DEFAULT now(),
  description text,
  CONSTRAINT audit_logs_pkey PRIMARY KEY (id),
  CONSTRAINT fk_business FOREIGN KEY (business_id) REFERENCES public.businesses(id),
  CONSTRAINT fk_user FOREIGN KEY (user_id) REFERENCES public.users(id)
);

-- Create auth_logs (depends on users)
CREATE TABLE public.auth_logs (
  id uuid NOT NULL DEFAULT uuid_generate_v4(),
  user_id uuid,
  ip_address inet,
  user_agent text,
  action character varying,
  status character varying,
  created_at timestamp with time zone DEFAULT now(),
  details jsonb,
  CONSTRAINT auth_logs_pkey PRIMARY KEY (id),
  CONSTRAINT auth_logs_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id)
);

-- Create role_audit_logs (depends on users)
CREATE TABLE public.role_audit_logs (
  id uuid NOT NULL DEFAULT uuid_generate_v4(),
  user_id uuid,
  action character varying NOT NULL,
  target_type character varying,
  target_id uuid,
  old_values jsonb,
  new_values jsonb,
  ip_address inet,
  user_agent text,
  created_at timestamp with time zone DEFAULT now(),
  CONSTRAINT role_audit_logs_pkey PRIMARY KEY (id),
  CONSTRAINT role_audit_logs_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id)
);

-- Create product_audit_logs (depends on businesses, products, and users)
CREATE TABLE public.product_audit_logs (
  id uuid NOT NULL DEFAULT uuid_generate_v4(),
  business_id uuid NOT NULL,
  product_id uuid NOT NULL,
  user_id uuid,
  action_type character varying NOT NULL,
  field_name character varying,
  old_value text,
  new_value text,
  notes text,
  ip_address inet,
  user_agent text,
  created_at timestamp with time zone DEFAULT now(),
  CONSTRAINT product_audit_logs_pkey PRIMARY KEY (id),
  CONSTRAINT product_audit_logs_business_id_fkey FOREIGN KEY (business_id) REFERENCES public.businesses(id),
  CONSTRAINT product_audit_logs_product_id_fkey FOREIGN KEY (product_id) REFERENCES public.products(id),
  CONSTRAINT product_audit_logs_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id)
);

-- Create product_batch_updates (depends on businesses and users)
CREATE TABLE public.product_batch_updates (
  id uuid NOT NULL DEFAULT uuid_generate_v4(),
  business_id uuid NOT NULL,
  updated_by uuid,
  update_type character varying NOT NULL,
  notes text,
  created_at timestamp with time zone DEFAULT now(),
  CONSTRAINT product_batch_updates_pkey PRIMARY KEY (id),
  CONSTRAINT product_batch_updates_business_id_fkey FOREIGN KEY (business_id) REFERENCES public.businesses(id),
  CONSTRAINT product_batch_updates_updated_by_fkey FOREIGN KEY (updated_by) REFERENCES public.users(id)
);

-- Create product_batch_update_items (depends on product_batch_updates and products)
CREATE TABLE public.product_batch_update_items (
  id uuid NOT NULL DEFAULT uuid_generate_v4(),
  batch_update_id uuid NOT NULL,
  product_id uuid NOT NULL,
  field_name character varying NOT NULL,
  old_value text,
  new_value text,
  created_at timestamp with time zone DEFAULT now(),
  CONSTRAINT product_batch_update_items_pkey PRIMARY KEY (id),
  CONSTRAINT product_batch_update_items_batch_update_id_fkey FOREIGN KEY (batch_update_id) REFERENCES public.product_batch_updates(id),
  CONSTRAINT product_batch_update_items_product_id_fkey FOREIGN KEY (product_id) REFERENCES public.products(id)
);

-- Create product_import_logs (depends on businesses and users)
CREATE TABLE public.product_import_logs (
  id uuid NOT NULL DEFAULT uuid_generate_v4(),
  business_id uuid NOT NULL,
  import_batch_id uuid NOT NULL,
  file_name character varying,
  total_rows integer,
  success_count integer DEFAULT 0,
  failed_count integer DEFAULT 0,
  error_log text,
  imported_by uuid,
  created_at timestamp with time zone DEFAULT now(),
  CONSTRAINT product_import_logs_pkey PRIMARY KEY (id),
  CONSTRAINT product_import_logs_business_id_fkey FOREIGN KEY (business_id) REFERENCES public.businesses(id),
  CONSTRAINT product_import_logs_imported_by_fkey FOREIGN KEY (imported_by) REFERENCES public.users(id)
);

-- Create product_variant_options (depends on products and product_attribute_values)
CREATE TABLE public.product_variant_options (
  id uuid NOT NULL DEFAULT uuid_generate_v4(),
  product_id uuid NOT NULL,
  attribute_value_id uuid NOT NULL,
  created_at timestamp with time zone DEFAULT now(),
  CONSTRAINT product_variant_options_pkey PRIMARY KEY (id),
  CONSTRAINT product_variant_options_product_id_fkey FOREIGN KEY (product_id) REFERENCES public.products(id),
  CONSTRAINT product_variant_options_attribute_value_id_fkey FOREIGN KEY (attribute_value_id) REFERENCES public.product_attribute_values(id)
);
