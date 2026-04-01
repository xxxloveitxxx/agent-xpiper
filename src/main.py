# Simple HTML generator for business context input
def generate_business_input_page(business_url: str):
    html = f"""
    <!DOCTYPE html>
    <html>
    <head><title>Business Context</title></head>
    <body>
        <h1>📋 Lead Gen Business Context</h1>
        <form action="/analyze" method="POST">
            <label>Your Business URL: <input name="business_url" value="{business_url}" required></label><br><br>
            <label>Min Properties for Sale: <input name="min_properties" value="5" type="number"></label><br><br>
            <label>Target Keywords: <input name="keywords" placeholder="luxury,investor"></label><br><br>
            <button type="submit">🚀 Start Agent Pipeline</button>
        </form>
    </body>
    </html>
    """
    
    with open('output/business_context.html', 'w') as f:
        f.write(html)
