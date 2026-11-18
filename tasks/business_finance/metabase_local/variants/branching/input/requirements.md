# Business Analytics Dashboard — Requirements Document

## Objective

Build a comprehensive business analytics dashboard in Metabase using the pre-loaded
"Business Analytics" SQLite database. The dashboard must answer the key business 
questions listed below and present the findings through appropriate visualizations.

## Database Schema

The "Business Analytics" database contains four tables:

### customers (500 rows)
| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER | Primary key |
| first_name | TEXT | Customer first name |
| last_name | TEXT | Customer last name |
| email | TEXT | Email address (unique) |
| city | TEXT | City |
| state | TEXT | US state code |
| country | TEXT | Country (all US) |
| signup_date | TEXT | Date joined (YYYY-MM-DD) |
| acquisition_channel | TEXT | How they found us |
| lifetime_value | REAL | Total completed order value |

### products (50 rows)
| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER | Primary key |
| name | TEXT | Product name |
| category | TEXT | One of: Electronics, Clothing, Home & Garden, Books, Sports |
| price | REAL | Selling price |
| cost | REAL | Cost of goods |
| sku | TEXT | Stock keeping unit (unique) |

### orders (5000 rows)
| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER | Primary key |
| customer_id | INTEGER | Foreign key to customers |
| product_id | INTEGER | Foreign key to products |
| quantity | INTEGER | Units ordered |
| unit_price | REAL | Price per unit at time of order |
| total_amount | REAL | quantity * unit_price |
| order_date | TEXT | Order date (YYYY-MM-DD), range: 2024-01 to 2024-12 |
| status | TEXT | completed, shipped, refunded, or cancelled |
| device | TEXT | desktop, mobile, or tablet |
| channel | TEXT | Acquisition channel |

### events (20000 rows)
| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER | Primary key |
| customer_id | INTEGER | Foreign key to customers |
| event_type | TEXT | page_view, product_view, add_to_cart, checkout_start, purchase |
| event_date | TEXT | Event date (YYYY-MM-DD) |
| page_url | TEXT | Page URL path |
| device | TEXT | desktop, mobile, or tablet |
| channel | TEXT | Acquisition channel |
| session_id | TEXT | Session identifier |

## Required Dashboard Components

### Chart 1: Monthly Revenue Trend (Line Chart)
- Show total revenue per month for completed orders throughout 2024
- X-axis: month (Jan 2024 to Dec 2024)
- Y-axis: revenue in dollars
- Use the visual query builder (not SQL) to create this chart

### Chart 2: Revenue by Product Category (Pie or Bar Chart)
- Show revenue breakdown by product category for completed orders
- Include all 5 categories
- Use the visual query builder

### Chart 3: Top 10 Customers by Lifetime Value (Table or Bar Chart)
- Display the top 10 customers ranked by their lifetime_value field
- Show customer name (first + last) and lifetime value amount
- Sorted descending by lifetime value

### Chart 4: Conversion Funnel (Bar or Funnel Chart)
- Show event counts for each funnel stage from the events table
- Stages: page_view → product_view → add_to_cart → checkout_start → purchase
- This helps visualize where users drop off

### Chart 5: Orders by Device Type (Pie Chart)
- Show the distribution of completed orders across device types
- Include: desktop, mobile, tablet

### Chart 6: Orders by Acquisition Channel (Bar Chart)
- Show the distribution of completed orders across acquisition channels
- Include all channels: organic_search, paid_search, social_media, email, referral, direct
- Sorted by count descending

## Additional Metrics (computed from the data, not requiring separate charts)

Some metrics in the output schema do not correspond to individual charts but must be
computed from the data:
- total_revenue: Sum of total_amount for all completed orders
- total_completed_orders: Count of completed orders
- average_order_value: Average total_amount for completed orders
- unique_purchasing_customers: Count of distinct customers with completed orders
- conversion_rate: (purchase event count / page_view event count) * 100

These can be derived from the chart data or by running additional queries in Metabase.

## Dashboard Assembly Requirements

- Create a new dashboard named "Business Analytics Overview"
- Add all 5 charts to the dashboard
- Add a text/heading card with the dashboard title
- Arrange charts in a logical layout

## Output

After building the dashboard, export the key metrics as a JSON file.

Save to: the output directory named in the task prompt (output/dashboard_metrics.json).

The JSON must conform to the schema defined in output_schema.json.
All numerical values must be rounded to 2 decimal places.
Revenue calculations must only include orders with status = 'completed'.
