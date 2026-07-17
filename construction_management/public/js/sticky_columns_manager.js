// Copyright (c) 2024, Construction Management
// License: MIT
// Enhanced Sticky Columns Manager - Manages left-side sticky columns

/**
 * Enhanced Sticky Columns Manager
 * Manages sticky column behavior for Rate, Amount, and Total columns
 * Extends the existing Total Qty sticky column implementation
 */
class StickyColumnsManager {
	constructor() {
		this.stickyColumns = [
			{ name: 'expand', width: 40, selector: '.col-expand' },
			{ name: 'checkbox', width: 40, selector: '.col-checkbox' },
			{ name: 'srno', width: 52, selector: '.col-srno' },
			{ name: 'desc', width: 250, selector: '.col-desc' },
			{ name: 'unit', width: 60, selector: '.col-unit' },
			{ name: 'total-qty', width: 100, selector: '.col-total-qty' },
			{ name: 'rate', width: 120, selector: '.col-rate' },
			{ name: 'amount', width: 140, selector: '.col-amount' }
		];

		this.isInitialized = false;
		this.currentPositions = new Map();
		this.resizeObserver = null;

		// Bind methods
		this.handleScroll = this.handleScroll.bind(this);
		this.handleResize = this.handleResize.bind(this);
	}

	/**
	 * Initialize sticky columns system
	 * @param {jQuery} container - Table container element
	 */
	initializeStickyColumns(container) {
		if (this.isInitialized) {
			this.cleanup();
		}

		this.container = container;
		this.calculateColumnPositions();
		this.applyStickyStyles();
		this.setupEventListeners();
		this.isInitialized = true;

		console.log('Enhanced Sticky Columns Manager initialized');
	}

	/**
	 * Calculate left positions for sticky columns
	 */
	calculateColumnPositions() {
		let currentLeft = 0;
		
		this.stickyColumns.forEach((column) => {
			const headerCell = this.container ? this.container.find('thead ' + column.selector).first() : null;
			const bodyCell = this.container ? this.container.find('tbody ' + column.selector).first() : null;
			const headerWidth = headerCell && headerCell.length ? headerCell.outerWidth() : 0;
			const bodyWidth = bodyCell && bodyCell.length ? bodyCell.outerWidth() : 0;
			const measuredWidth = Math.max(headerWidth, bodyWidth);

			// Use the widest cell so sticky offsets stay aligned even when row content is wider
			column.computedWidth = measuredWidth > 0 ? measuredWidth : column.width;
			this.currentPositions.set(column.name, currentLeft);
			currentLeft += column.computedWidth;
		});
		
		// Mark the last sticky column
		this.lastStickyColumn = this.stickyColumns[this.stickyColumns.length - 1].name;
	}

	/**
	 * Apply sticky column styles
	 */
	applyStickyStyles() {
		if (!this.container) return;

		// Remove existing sticky styles
		this.removeStickyStyles();

		// Generate and apply new styles
		const styles = this.generateStickyStyles();

		if (!$('#enhanced-sticky-styles').length) {
			$('head').append(`<style id="enhanced-sticky-styles">${styles}</style>`);
		} else {
			$('#enhanced-sticky-styles').html(styles);
		}

		// Apply sticky classes to elements
		this.applyStickyClasses();
	}

	/**
	 * Generate CSS styles for sticky columns
	 * @returns {string} CSS styles
	 */
	generateStickyStyles() {
		let styles = `
			/* Enhanced Sticky Columns System */
			.enhanced-sticky-col {
				position: sticky;
				background: #fff;
				z-index: 2;
				border-right: 1px solid #e8e8e8;
			}
			
			.comprehensive-items-table th.enhanced-sticky-col {
				background: #f7f7f7;
				z-index: 3;
			}
			
			.comprehensive-items-table tr:hover .enhanced-sticky-col {
				background: #fafbfc;
			}
			
			/* Row status background colors for sticky columns */
			.row-status-pc-pending .enhanced-sticky-col {
				background-color: #fff3e0 !important;
			}
			
			.row-status-pc-pending:hover .enhanced-sticky-col {
				background-color: #ffe0b2 !important;
			}
			
			.row-status-invoice-pending .enhanced-sticky-col {
				background-color: #e3f2fd !important;
			}
			
			.row-status-invoice-pending:hover .enhanced-sticky-col {
				background-color: #bbdefb !important;
			}
		`;

		// Generate position styles for each sticky column
		this.stickyColumns.forEach((column) => {
			const position = this.currentPositions.get(column.name);
			styles += `
				${column.selector}.enhanced-sticky-col {
					left: ${position}px;
					min-width: ${column.computedWidth || column.width}px;
					width: ${column.computedWidth || column.width}px;
				}
			`;
		});

		// Add visual separation for the last sticky column
		const lastColumnSelector = this.stickyColumns[this.stickyColumns.length - 1].selector;
		styles += `
			${lastColumnSelector}.enhanced-sticky-col.sticky-col-last {
				border-right: 2px solid #ccc !important;
				box-shadow: 2px 0 4px rgba(0,0,0,0.1);
				margin-right: 8px;
				transition: border-color 0.2s ease, box-shadow 0.2s ease;
			}
		`;

		// Responsive adjustments
		styles += `
			@media (max-width: 1366px) {
				.col-desc.enhanced-sticky-col {
					min-width: 150px;
					width: 150px;
				}
			}
			
			@media (max-width: 1024px) {
				.col-desc.enhanced-sticky-col {
					min-width: 120px;
					width: 120px;
				}
				
				.col-rate.enhanced-sticky-col,
				.col-amount.enhanced-sticky-col {
					min-width: 70px;
					width: 70px;
				}
			}
		`;

		return styles;
	}

	/**
	 * Apply sticky classes to table elements
	 */
	applyStickyClasses() {
		if (!this.container) return;

		// Apply sticky classes to headers and cells
		this.stickyColumns.forEach((column) => {
			const elements = this.container.find(column.selector);
			elements.addClass('enhanced-sticky-col');

			// Add sticky-col-last class to the last column
			if (column.name === this.lastStickyColumn) {
				elements.addClass('sticky-col-last');
			}
		});
	}

	/**
	 * Remove sticky styles and classes
	 */
	removeStickyStyles() {
		if (!this.container) return;

		// Remove sticky classes
		this.stickyColumns.forEach((column) => {
			const elements = this.container.find(column.selector);
			elements.removeClass('enhanced-sticky-col sticky-col-last');
		});
	}

	/**
	 * Setup event listeners
	 */
	setupEventListeners() {
		// Scroll handling for performance optimization
		if (this.container) {
			this.container.find('.comprehensive-table-wrapper').on('scroll', this.handleScroll);
		}

		// Resize handling
		$(window).on('resize.sticky-columns', this.handleResize);

		// Setup resize observer for container size changes
		if (window.ResizeObserver && this.container[0]) {
			this.resizeObserver = new ResizeObserver(this.handleResize);
			this.resizeObserver.observe(this.container[0]);
		}
	}

	/**
	 * Handle scroll events
	 * @param {Event} e - Scroll event
	 */
	handleScroll(e) {
		// Throttle scroll handling for performance
		if (this.scrollTimeout) return;

		this.scrollTimeout = setTimeout(() => {
			this.updateStickyVisibility();
			this.scrollTimeout = null;
		}, 16); // ~60fps
	}

	/**
	 * Handle resize events
	 */
	handleResize() {
		// Debounce resize handling
		clearTimeout(this.resizeTimeout);
		this.resizeTimeout = setTimeout(() => {
			this.recalculatePositions();
		}, 250);
	}

	/**
	 * Update sticky column visibility based on scroll position
	 */
	updateStickyVisibility() {
		if (!this.container) return;

		const wrapper = this.container.find('.comprehensive-table-wrapper');
		const scrollLeft = wrapper.scrollLeft();

		// Add visual feedback for scrolled state
		if (scrollLeft > 0) {
			this.container.addClass('table-scrolled');
		} else {
			this.container.removeClass('table-scrolled');
		}
	}

	/**
	 * Recalculate positions when container size changes
	 */
	recalculatePositions() {
		if (!this.isInitialized) return;

		// Recalculate based on current container width
		this.calculateColumnPositions();
		this.applyStickyStyles();
	}

	/**
	 * Add new sticky column dynamically
	 * @param {Object} columnConfig - Column configuration
	 */
	addStickyColumn(columnConfig) {
		const { name, width, selector, insertAfter } = columnConfig;

		if (this.stickyColumns.find(col => col.name === name)) {
			console.warn(`Sticky column '${name}' already exists`);
			return;
		}

		const newColumn = { name, width, selector };

		if (insertAfter) {
			const insertIndex = this.stickyColumns.findIndex(col => col.name === insertAfter);
			if (insertIndex !== -1) {
				this.stickyColumns.splice(insertIndex + 1, 0, newColumn);
			} else {
				this.stickyColumns.push(newColumn);
			}
		} else {
			this.stickyColumns.push(newColumn);
		}

		// Recalculate and apply
		this.recalculatePositions();
	}

	/**
	 * Remove sticky column
	 * @param {string} columnName - Name of column to remove
	 */
	removeStickyColumn(columnName) {
		const columnIndex = this.stickyColumns.findIndex(col => col.name === columnName);

		if (columnIndex === -1) {
			console.warn(`Sticky column '${columnName}' not found`);
			return;
		}

		// Remove sticky classes from elements
		const column = this.stickyColumns[columnIndex];
		if (this.container) {
			this.container.find(column.selector).removeClass('enhanced-sticky-col sticky-col-last');
		}

		// Remove from array
		this.stickyColumns.splice(columnIndex, 1);

		// Recalculate positions
		this.recalculatePositions();
	}

	/**
	 * Update column width
	 * @param {string} columnName - Name of column to update
	 * @param {number} newWidth - New width in pixels
	 */
	updateColumnWidth(columnName, newWidth) {
		const column = this.stickyColumns.find(col => col.name === columnName);

		if (!column) {
			console.warn(`Sticky column '${columnName}' not found`);
			return;
		}

		column.width = newWidth;
		this.recalculatePositions();
	}

	/**
	 * Get current sticky column configuration
	 * @returns {Array} Current sticky columns configuration
	 */
	getStickyColumns() {
		return [...this.stickyColumns];
	}

	/**
	 * Check if sticky columns are properly positioned
	 * @returns {boolean} True if properly positioned
	 */
	validatePositioning() {
		if (!this.container) return false;

		let isValid = true;

		this.stickyColumns.forEach((column) => {
			const elements = this.container.find(column.selector + '.enhanced-sticky-col');
			const expectedPosition = this.currentPositions.get(column.name);

			elements.each((i, el) => {
				const actualPosition = parseInt($(el).css('left'), 10);
				if (actualPosition !== expectedPosition) {
					console.warn(`Column ${column.name} position mismatch: expected ${expectedPosition}, actual ${actualPosition}`);
					isValid = false;
				}
			});
		});

		return isValid;
	}

	/**
	 * Cleanup event listeners and observers
	 */
	cleanup() {
		// Remove event listeners
		if (this.container) {
			this.container.find('.comprehensive-table-wrapper').off('scroll', this.handleScroll);
		}

		$(window).off('resize.sticky-columns');
		$(document).off('.sticky-columns');

		// Disconnect resize observer
		if (this.resizeObserver) {
			this.resizeObserver.disconnect();
			this.resizeObserver = null;
		}

		// Remove styles
		$('#enhanced-sticky-styles').remove();

		// Remove sticky classes
		this.removeStickyStyles();

		// Clear timeouts
		clearTimeout(this.resizeTimeout);
		clearTimeout(this.scrollTimeout);

		this.isInitialized = false;
		this.container = null;
	}

	/**
	 * Reinitialize sticky columns (useful after table re-render)
	 * @param {jQuery} container - New table container
	 */
	reinitialize(container) {
		this.cleanup();
		this.initializeStickyColumns(container);
	}

	/**
	 * Get debug information
	 * @returns {Object} Debug information
	 */
	getDebugInfo() {
		return {
			isInitialized: this.isInitialized,
			stickyColumns: this.stickyColumns,
			currentPositions: Object.fromEntries(this.currentPositions),
			lastStickyColumn: this.lastStickyColumn,
			containerExists: !!this.container,
			validationResult: this.validatePositioning()
		};
	}
}

// Create global instance
window.stickyColumnsManager = new StickyColumnsManager();

// Enhanced integration with existing BOQ table rendering
const originalRenderBOQTable = window.render_boq_management_table;
if (originalRenderBOQTable) {
	window.render_boq_management_table = function (container, frm, bills) {
		// Call original function
		const result = originalRenderBOQTable.call(this, container, frm, bills);

		// Initialize enhanced sticky columns
		setTimeout(() => {
			window.stickyColumnsManager.initializeStickyColumns(container);
		}, 100);

		return result;
	};
}

// Export for module usage
if (typeof module !== 'undefined' && module.exports) {
	module.exports = StickyColumnsManager;
}
