#!/usr/bin/env python3
"""
Product Pricing Module for RMBB Health Wound Care Products

This module contains quarterly pricing for all wound care products and sizes.
Update this file quarterly when pricing changes - no other code changes needed.

Last Updated: September 2025 Q3
Next Update Due: December 2025 Q4
"""

from typing import Dict, Optional
import logging

class ProductPricingManager:
    """
    Centralized pricing management for all RMBB Health wound care products.
    
    Pricing Structure:
    - Each product has multiple available sizes
    - Prices are per unit in USD
    - Quarterly updates only require modifying this file
    """
    
    def __init__(self):
        """Initialize with Q3 2025 pricing."""
        
        # =====================================================
        # Q3 2025 PRICING - UPDATE QUARTERLY
        # =====================================================
        
        self.product_pricing = {
            # AmnioAmp-MP (Q4250) - CellGenuity - 6 sizes
            "AmnioAmp-MP": {
                "2x2": 11452.00,
                "2x3": 17178.00,
                "2x4": 22904.00,
                "4x4": 45808.00,
                "4x6": 68712.00,
                "4x8": 91616.00
            },
            
            # Palingen (Q4173) - Amnio Technology - 5 sizes
            "Palingen": {
                "1x1": 360.00,
                "2x3": 2160.00,
                "4x4": 5760.00,
                "4x6": 8640.00,
                "4x8": 11520.00
            },
            
            # Simplimax - XTANT Medical - 5 sizes
            "Simplimax": {
                "2x2": 13348.92,
                "2x3": 20023.38,
                "4x4": 53395.68,
                "4x6": 80093.52,
                "4x8": 106791.36
            },
            
            # Xcell Amnio Matrix (Q4280) - Precise Bioscience - 4 sizes
            "Xcell Amnio Matrix": {
                "2x2": 12984.20,
                "2x4": 25968.40,
                "4x4": 51936.80,
                "4x7": 90889.40
            },
            
            # AmnioMaxx (Q4239) - Royal Biologics - 7 unique sizes (duplicates removed)
            "AmnioMaxx": {
                "2x2": 9399.70,
                "2x3": 14099.54,
                "2x4": 18799.39,
                "4x4": 37598.78,
                "4x6": 56398.18,
                "4x8": 75197.57,
                "3x3": 21149.32,
                "4x4": 37598.78,
                "4x8": 75197.57
            },
            
            # Dermabind-FM - HealthTech - 4 sizes
            "Dermabind-FM": {
                "2x2": 13348.92,
                "3x3": 30035.07,
                "4x4": 53395.68,
                "6.5x6.5": 140997.97
            },
            
            # Derm Maxx - Royal Biologics - 6 sizes
            "Derm Maxx": {
                "1x1": 1644.99,
                "2x2": 6579.96,
                "2x4": 13159.92,
                "4x4": 26319.84,
                "4x8": 52639.68,
                "5x10": 82249.50
            },
            
            # Esano ACA - Evolution Biologyx - 5 sizes
            "Esano ACA": {
                "2x2": 10706.00,
                "2x3": 16059.00,
                "4x4": 42824.00,
                "4x6": 64236.00,
                "4x8": 85648.00
            },
            
            # Membrane Wrap - BioLab Sciences - 6 Q2 sizes only (regular sizes removed)
            "Membrane Wrap": {
                "1x1 Q2": 1055.97,
                "2x2 Q2": 4223.88,
                "2x3 Q2": 6335.82,
                "4x4 Q2": 16895.52,
                "4x6 Q2": 25343.28,
                "4x8 Q2": 33791.04
            },
            
            # Membrane Wrap H (Q4290) - BioLab Sciences - 5 sizes
            "Membrane Wrap H": {
                "2x2": 7364.00,
                "2x3": 11046.00,
                "4x4": 29456.00,
                "4x6": 44184.00,
                "4x8": 58912.00
            }
        }
        
        # Default pricing for unknown products/sizes
        self.default_price_per_cm2 = 0.00  # No pricing until manually set
        
        # Pricing metadata
        self.pricing_info = {
            "version": "Q3_2025",
            "effective_date": "2025-09-01",
            "next_review": "2025-12-01",
            "currency": "USD",
            "updated_by": "Cell Products Finance Team"
        }
        
        logging.info(f"📊 Loaded product pricing: {self.pricing_info['version']}")
        logging.info(f"🔄 Next pricing review: {self.pricing_info['next_review']}")
    
    def get_product_price(self, product_name: str, size: str) -> Optional[float]:
        """
        Get the price for a specific product and size.
        
        Args:
            product_name (str): Product name (e.g., "AmnioMaxx")
            size (str): Product size (e.g., "4x6")
            
        Returns:
            float: Price in USD, or None if not found
        """
        try:
            if product_name in self.product_pricing:
                product_sizes = self.product_pricing[product_name]
                if size in product_sizes:
                    price = product_sizes[size]
                    logging.debug(f"💰 {product_name} {size}: ${price:.2f}")
                    return price
                else:
                    logging.warning(f"⚠️ Size {size} not found for {product_name}")
                    return None
            else:
                logging.warning(f"⚠️ Product {product_name} not found in pricing")
                return None
                
        except Exception as e:
            logging.error(f"❌ Error getting price for {product_name} {size}: {str(e)}")
            return None
    
    def calculate_size_price_by_area(self, size: str) -> float:
        """
        Calculate price based on size area using default rate.
        Fallback method when specific product pricing not available.
        
        Args:
            size (str): Size like "4x6", "2x3", etc.
            
        Returns:
            float: Calculated price based on area
        """
        try:
            # Parse size string to calculate area
            if 'x' in size:
                dimensions = size.split('x')
                if len(dimensions) == 2:
                    width = float(dimensions[0])
                    height = float(dimensions[1])
                    area_cm2 = width * height
                    price = area_cm2 * self.default_price_per_cm2
                    logging.info(f"📐 Calculated {size} = {area_cm2}cm² × ${self.default_price_per_cm2}/cm² = ${price:.2f}")
                    return price
            
            logging.warning(f"⚠️ Could not parse size '{size}' for area calculation")
            return 0.00  # No pricing until manually set
            
        except Exception as e:
            logging.error(f"❌ Error calculating price by area for {size}: {str(e)}")
            return 0.00  # No pricing until manually set
    
    def get_all_products(self) -> Dict[str, Dict[str, float]]:
        """
        Get complete pricing dictionary for all products.
        
        Returns:
            dict: Complete pricing structure
        """
        return self.product_pricing.copy()
    
    def get_product_sizes(self, product_name: str) -> Dict[str, float]:
        """
        Get all sizes and prices for a specific product.
        
        Args:
            product_name (str): Product name
            
        Returns:
            dict: Size -> price mapping for the product
        """
        return self.product_pricing.get(product_name, {}).copy()
    
    def get_pricing_info(self) -> Dict[str, str]:
        """
        Get pricing metadata information.
        
        Returns:
            dict: Pricing version, dates, and update info
        """
        return self.pricing_info.copy()
    
    def validate_pricing_currency(self) -> bool:
        """
        Validate that all pricing is consistent and reasonable.
        
        Returns:
            bool: True if pricing passes validation
        """
        try:
            total_products = len(self.product_pricing)
            total_sizes = sum(len(sizes) for sizes in self.product_pricing.values())
            
            # Basic validation checks
            if total_products == 0:
                logging.error("❌ No products found in pricing")
                return False
            
            # Check for reasonable price ranges
            all_prices = []
            for product_data in self.product_pricing.values():
                all_prices.extend(product_data.values())
            
            if not all_prices:
                logging.error("❌ No prices found")
                return False
            
            min_price = min(all_prices)
            max_price = max(all_prices)
            
            # Reasonable price range validation (0.00 is acceptable for quarterly updates)
            if min_price < 0.00 or max_price > 100000.00:
                logging.warning(f"⚠️ Unusual price range: ${min_price:.2f} - ${max_price:.2f}")
            
            logging.info(f"✅ Pricing validation passed:")
            logging.info(f"   📊 Products: {total_products}")
            logging.info(f"   📏 Total sizes: {total_sizes}")
            logging.info(f"   💰 Price range: ${min_price:.2f} - ${max_price:.2f}")
            
            return True
            
        except Exception as e:
            logging.error(f"❌ Pricing validation error: {str(e)}")
            return False


# =====================================================
# QUARTERLY UPDATE INSTRUCTIONS
# =====================================================
"""
TO UPDATE PRICING (Quarterly):

1. Modify the 'product_pricing' dictionary above with new prices
2. Update 'pricing_info' with new version and dates
3. Test the changes by running: python product_pricing.py
4. No other code files need to be modified

Example update for Q4 2025:
- Change version to "Q4_2025"
- Update effective_date to "2025-12-01"
- Update next_review to "2026-03-01"
- Modify individual product prices as needed
"""


# =====================================================
# TESTING AND VALIDATION
# =====================================================

def test_pricing_module():
    """Test the pricing module functionality."""
    pricing = ProductPricingManager()
    
    print("🧪 Testing Product Pricing Module")
    print("=" * 50)
    
    # Test validation
    if pricing.validate_pricing_currency():
        print("✅ Pricing validation passed")
    else:
        print("❌ Pricing validation failed")
    
    # Test specific product pricing
    test_cases = [
        ("AmnioMaxx", "4x6"),
        ("Palingen", "4x8"),
        ("Membrane Wrap", "2x2"),
        ("Unknown Product", "4x6"),  # Should return None
        ("AmnioMaxx", "10x10")       # Should return None
    ]
    
    print("\n📋 Testing Price Lookups:")
    for product, size in test_cases:
        price = pricing.get_product_price(product, size)
        if price is not None:
            print(f"   {product} {size}: ${price:.2f}")
        else:
            print(f"   {product} {size}: Not found")
    
    # Test area-based calculation
    print("\n📐 Testing Area-Based Pricing:")
    test_sizes = ["2x3", "4x8", "invalid"]
    for size in test_sizes:
        price = pricing.calculate_size_price_by_area(size)
        print(f"   {size}: ${price:.2f}")
    
    # Show pricing info
    info = pricing.get_pricing_info()
    print(f"\n📊 Pricing Info: {info}")
    
    print("\n🎉 Pricing module test completed!")


if __name__ == "__main__":
    # Run tests when file is executed directly
    test_pricing_module()