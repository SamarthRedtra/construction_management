/**
 * Profit/Loss Indicator Component
 * Displays visual profit/loss indicators with color coding in BOQ item rows
 * Part of Phase 3: UI/UX Improvements
 * 
 * Requirements: 8.1, 8.2, 8.3, 8.4, 8.5
 */

class ProfitLossIndicator {
	constructor() {
		this.indicators = new Map();
		this.colorScheme = {
			profit: '#28a745',      // Green
			loss: '#dc3545',        // Red
			breakEven: '#ffc107',   // Yellow/Amber
			noData: '#6c757d'       // Gray
		};
	}

	/**
	 * Calculate profit status for a BOQ item
	 * @param {Object} item - BOQ item with cost and revenue data
	 * @returns {Object} Profit status with amount and percentage
	 */
	calculateProfitStatus(item) {
		const revenue = parseFloat(item.total_amount || 0);
		const cost = parseFloat(item.total_estimated_cost || 0);
		
		// If no cost data, return no data status
		if (cost === 0 && revenue === 0) {
			return {
				status: 'no_data',
				profit: 0,
				profitPercent: 0,
				revenue: 0,
				cost: 0,
				message: 'No cost/revenue data'
			};
		}
		
		const profit = revenue - cost;
		const profitPercent = revenue > 0 ? (profit / revenue * 100) : 0;
		
		let status;
		if (Math.abs(profit) < 0.01) {
			status = 'break_even';
		} else if (profit > 0) {
			status = 'profit';
		} else {
			status = 'loss';
		}
		
		return {
			status: status,
			profit: profit,
			profitPercent: profitPercent,
			revenue: revenue,
			cost: cost,
			message: this._getStatusMessage(status, profit, profitPercent)
		};
	}

	/**
	 * Get status message for display
	 * @private
	 */
	_getStatusMessage(status, profit, profitPercent) {
		if (status === 'no_data') {
			return 'No data';
		} else if (status === 'break_even') {
			return 'Break Even';
		} else if (status === 'profit') {
			return `Profit: ${this._formatCurrency(profit)} (${profitPercent.toFixed(1)}%)`;
		} else {
			return `Loss: ${this._formatCurrency(Math.abs(profit))} (${Math.abs(profitPercent).toFixed(1)}%)`;
		}
	}

	/**
	 * Create indicator HTML element
	 * @param {Object} profitStatus - Profit status object
	 * @param {string} itemId - BOQ item ID
	 * @returns {string} HTML string for indicator
	 */
	createIndicatorHTML(profitStatus, itemId) {
		const color = this.colorScheme[profitStatus.status];
		const icon = this._getStatusIcon(profitStatus.status);
		
		return `
			<div class="profit-loss-indicator" 
				 data-item-id="${itemId}"
				 data-status="${profitStatus.status}"
				 style="display: flex; align-items: center; gap: 8px; padding: 4px 8px; 
				        background-color: ${color}15; border-left: 3px solid ${color}; 
				        border-radius: 4px; font-size: 12px;">
				<span style="color: ${color}; font-size: 16px;">${icon}</span>
				<div style="flex: 1;">
					<div style="display: flex; justify-content: space-between; align-items: center;">
						<span style="font-weight: 600; color: ${color};">
							${profitStatus.status === 'profit' ? 'Profit' : 
							  profitStatus.status === 'loss' ? 'Loss' : 
							  profitStatus.status === 'break_even' ? 'Break Even' : 'No Data'}
						</span>
						<span style="font-weight: 700; color: ${color};">
							${this._formatCurrency(Math.abs(profitStatus.profit))}
						</span>
					</div>
					<div style="display: flex; justify-content: space-between; font-size: 11px; 
					            color: #666; margin-top: 2px;">
						<span>Revenue: ${this._formatCurrency(profitStatus.revenue)}</span>
						<span>Cost: ${this._formatCurrency(profitStatus.cost)}</span>
						<span style="color: ${color}; font-weight: 600;">
							${profitStatus.profitPercent.toFixed(1)}%
						</span>
					</div>
				</div>
			</div>
		`;
	}

	/**
	 * Get icon for status
	 * @private
	 */
	_getStatusIcon(status) {
		const icons = {
			profit: '▲',      // Up arrow
			loss: '▼',        // Down arrow
			break_even: '●',  // Circle
			no_data: '○'      // Empty circle
		};
		return icons[status] || '○';
	}

	/**
	 * Apply color coding to an element
	 * @param {HTMLElement} element - Element to apply color to
	 * @param {string} status - Profit status
	 */
	applyColorCoding(element, status) {
		if (!element) return;
		
		const color = this.colorScheme[status];
		element.style.borderLeftColor = color;
		element.style.backgroundColor = `${color}15`;
		
		// Add status class
		element.classList.remove('profit-status', 'loss-status', 'break-even-status', 'no-data-status');
		element.classList.add(`${status.replace('_', '-')}-status`);
	}

	/**
	 * Update indicators for multiple items
	 * @param {Array} items - Array of BOQ items
	 */
	updateIndicators(items) {
		if (!items || !Array.isArray(items)) return;
		
		items.forEach(item => {
			const profitStatus = this.calculateProfitStatus(item);
			const indicatorElement = document.querySelector(
				`.profit-loss-indicator[data-item-id="${item.name}"]`
			);
			
			if (indicatorElement) {
				// Update existing indicator
				indicatorElement.outerHTML = this.createIndicatorHTML(profitStatus, item.name);
			}
			
			// Store in map for quick access
			this.indicators.set(item.name, profitStatus);
		});
	}

	/**
	 * Add indicator to BOQ item row
	 * @param {string} itemId - BOQ item ID
	 * @param {HTMLElement} rowElement - Row element to add indicator to
	 * @param {Object} itemData - BOQ item data
	 */
	addIndicatorToRow(itemId, rowElement, itemData) {
		if (!rowElement || !itemData) return;
		
		const profitStatus = this.calculateProfitStatus(itemData);
		
		// Find the available space in the row (typically after description)
		// This is the empty space mentioned in requirements
		let targetContainer = rowElement.querySelector('.boq-item-details');
		
		if (!targetContainer) {
			// Create container if it doesn't exist
			targetContainer = document.createElement('div');
			targetContainer.className = 'boq-item-details';
			targetContainer.style.cssText = 'margin-top: 8px; padding: 0 12px;';
			
			// Insert after the main item content
			const mainContent = rowElement.querySelector('.boq-item-content');
			if (mainContent) {
				mainContent.parentNode.insertBefore(targetContainer, mainContent.nextSibling);
			} else {
				rowElement.appendChild(targetContainer);
			}
		}
		
		// Add indicator HTML
		const indicatorHTML = this.createIndicatorHTML(profitStatus, itemId);
		targetContainer.innerHTML = indicatorHTML;
		
		// Store in map
		this.indicators.set(itemId, profitStatus);
	}

	/**
	 * Update indicator when cost or revenue changes
	 * @param {string} itemId - BOQ item ID
	 * @param {Object} updatedData - Updated item data
	 */
	updateIndicator(itemId, updatedData) {
		const profitStatus = this.calculateProfitStatus(updatedData);
		const indicatorElement = document.querySelector(
			`.profit-loss-indicator[data-item-id="${itemId}"]`
		);
		
		if (indicatorElement) {
			indicatorElement.outerHTML = this.createIndicatorHTML(profitStatus, itemId);
		}
		
		this.indicators.set(itemId, profitStatus);
	}

	/**
	 * Get profit status for an item
	 * @param {string} itemId - BOQ item ID
	 * @returns {Object|null} Profit status or null if not found
	 */
	getIndicatorStatus(itemId) {
		return this.indicators.get(itemId) || null;
	}

	/**
	 * Clear all indicators
	 */
	clearIndicators() {
		this.indicators.clear();
		document.querySelectorAll('.profit-loss-indicator').forEach(el => el.remove());
	}

	/**
	 * Format currency value
	 * @private
	 */
	_formatCurrency(value) {
		return new Intl.NumberFormat('en-US', {
			style: 'currency',
			currency: frappe.boot.sysdefaults.currency || 'USD',
			minimumFractionDigits: 2,
			maximumFractionDigits: 2
		}).format(value);
	}

	/**
	 * Get summary statistics for all indicators
	 * @returns {Object} Summary with counts and totals
	 */
	getSummary() {
		const summary = {
			total: this.indicators.size,
			profit: 0,
			loss: 0,
			breakEven: 0,
			noData: 0,
			totalProfit: 0,
			totalLoss: 0,
			totalRevenue: 0,
			totalCost: 0
		};
		
		this.indicators.forEach(status => {
			summary[status.status === 'break_even' ? 'breakEven' : 
			        status.status === 'no_data' ? 'noData' : status.status]++;
			
			if (status.status === 'profit') {
				summary.totalProfit += status.profit;
			} else if (status.status === 'loss') {
				summary.totalLoss += Math.abs(status.profit);
			}
			
			summary.totalRevenue += status.revenue;
			summary.totalCost += status.cost;
		});
		
		return summary;
	}

	/**
	 * Create summary widget HTML
	 * @returns {string} HTML for summary widget
	 */
	createSummaryWidget() {
		const summary = this.getSummary();
		const netProfit = summary.totalProfit - summary.totalLoss;
		const netStatus = netProfit >= 0 ? 'profit' : 'loss';
		const netColor = this.colorScheme[netStatus];
		
		return `
			<div class="profit-loss-summary-widget" 
				 style="background: white; border: 1px solid #ddd; border-radius: 6px; 
				        padding: 12px; margin: 12px 0;">
				<div style="font-weight: 600; margin-bottom: 8px; color: #333;">
					Financial Summary
				</div>
				<div style="display: grid; grid-template-columns: repeat(2, 1fr); gap: 8px; 
				            font-size: 12px;">
					<div>
						<span style="color: #666;">Total Items:</span>
						<strong>${summary.total}</strong>
					</div>
					<div>
						<span style="color: ${this.colorScheme.profit};">Profitable:</span>
						<strong>${summary.profit}</strong>
					</div>
					<div>
						<span style="color: ${this.colorScheme.loss};">Loss-making:</span>
						<strong>${summary.loss}</strong>
					</div>
					<div>
						<span style="color: ${this.colorScheme.breakEven};">Break Even:</span>
						<strong>${summary.breakEven}</strong>
					</div>
				</div>
				<div style="margin-top: 12px; padding-top: 12px; border-top: 1px solid #eee;">
					<div style="display: flex; justify-content: space-between; margin-bottom: 4px;">
						<span style="color: #666;">Total Revenue:</span>
						<strong>${this._formatCurrency(summary.totalRevenue)}</strong>
					</div>
					<div style="display: flex; justify-content: space-between; margin-bottom: 4px;">
						<span style="color: #666;">Total Cost:</span>
						<strong>${this._formatCurrency(summary.totalCost)}</strong>
					</div>
					<div style="display: flex; justify-content: space-between; padding-top: 8px; 
					            border-top: 1px solid #eee;">
						<span style="font-weight: 600; color: ${netColor};">Net Profit/Loss:</span>
						<strong style="color: ${netColor}; font-size: 14px;">
							${this._formatCurrency(Math.abs(netProfit))}
							${netStatus === 'loss' ? '(Loss)' : ''}
						</strong>
					</div>
				</div>
			</div>
		`;
	}
}

// Export for use in other modules
if (typeof module !== 'undefined' && module.exports) {
	module.exports = ProfitLossIndicator;
}

// Make available globally
window.ProfitLossIndicator = ProfitLossIndicator;
