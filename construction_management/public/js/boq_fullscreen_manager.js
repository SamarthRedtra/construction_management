// Copyright (c) 2024, Construction Management
// License: MIT
// BOQ Full-Screen Manager - Enhanced full-screen BOQ expansion and UI stability

/**
 * BOQ Full-Screen Manager
 * Handles stable full-screen BOQ expansion, rendering, and UI behavior
 * Fixes issues with double-click requirements, partial rendering, and popup problems
 */
class BOQFullScreenManager {
	constructor() {
		this.isFullScreenActive = false;
		this.currentProject = null;
		this.originalScrollPosition = 0;
		this.modalElement = null;
		this.renderingInProgress = false;
		this.expansionStates = new Map(); // Track expansion states

		// Bind methods to maintain context
		this.handleKeydown = this.handleKeydown.bind(this);
		this.handleResize = this.handleResize.bind(this);
		this.handleModalClick = this.handleModalClick.bind(this);
	}

	/**
	 * Initialize full-screen BOQ view for a project
	 * @param {string} project - Project name
	 * @returns {Promise<void>}
	 */
	async initializeFullScreen(project) {
		if (this.renderingInProgress) {
			console.warn('BOQ Full-screen rendering already in progress');
			return;
		}

		try {
			this.renderingInProgress = true;
			this.currentProject = project;
			this.originalScrollPosition = window.pageYOffset;

			// Fetch BOQ data
			const data = await this.fetchBOQData(project);
			if (!data || !data.has_boq) {
				frappe.msgprint(__('No BOQ data found for this project'));
				return;
			}

			// Create and show full-screen modal
			await this.createFullScreenModal(project, data);
			this.isFullScreenActive = true;
			$('body').addClass('boq-modal-active');

			// Setup event listeners
			this.setupEventListeners();

		} catch (error) {
			console.error('Error initializing full-screen BOQ:', error);
			frappe.show_alert({
				message: __('Failed to load full-screen BOQ view'),
				indicator: 'red'
			});
		} finally {
			this.renderingInProgress = false;
		}
	}

	/**
	 * Fetch BOQ data from server
	 * @param {string} project - Project name
	 * @returns {Promise<Object>}
	 */
	fetchBOQData(project) {
		return new Promise((resolve, reject) => {
			frappe.call({
				method: 'construction_management.api.boq_tree.get_boq_tree_data',
				args: { project: project },
				callback: function (r) {
					if (r.message) {
						resolve(r.message);
					} else {
						reject(new Error('No data received'));
					}
				},
				error: function (err) {
					reject(err);
				}
			});
		});
	}

	/**
	 * Create full-screen modal with enhanced stability
	 * @param {string} project - Project name
	 * @param {Object} data - BOQ data
	 */
	async createFullScreenModal(project, data) {
		// Remove any existing modal
		this.closeFullScreen();

		// Create modal HTML
		const modalHtml = this.generateModalHTML(project);
		this.modalElement = $(modalHtml);

		// Add to DOM
		$('body').append(this.modalElement);

		// Apply styles
		this.applyFullScreenStyles();

		// Show modal with animation
		this.modalElement.hide().fadeIn(300);

		// Render BOQ content after modal is visible
		setTimeout(() => {
			this.adjustModalSize();
			this.renderBOQContent(data);
		}, 350); // Slight delay to ensure modal is fully rendered
	}

	/**
	 * Generate modal HTML structure
	 * @param {string} project - Project name
	 * @returns {string}
	 */
	generateModalHTML(project) {
		return `
			<div class="boq-fullscreen-modal" id="boq-fullscreen-modal">
				<div class="fullscreen-header">
					<div class="fullscreen-title">
						<h2>BOQ Management - Full Screen View</h2>
						<span class="project-name">${project}</span>
					</div>
					<div class="fullscreen-actions">
						<button class="btn btn-default btn-sm refresh-btn" title="Refresh Data">
							<i class="fa fa-refresh"></i> Refresh
						</button>
						<button class="btn btn-default btn-sm close-btn" title="Close Full Screen">
							<i class="fa fa-times"></i> Close
						</button>
					</div>
				</div>
				<div class="fullscreen-content">
					<div class="loading-container">
						<div class="loading-spinner"></div>
						<div class="loading-text">Loading BOQ data...</div>
					</div>
					<div id="fullscreen-bills-container" style="display: none;"></div>
				</div>
			</div>
		`;
	}

	/**
	 * Render BOQ content in full-screen modal
	 * @param {Object} data - BOQ data
	 */
	renderBOQContent(data) {
		try {
			const contentContainer = this.modalElement.find('#fullscreen-bills-container');
			const loadingContainer = this.modalElement.find('.loading-container');

			// Create mock frm object for compatibility
			const mockFrm = {
				doc: { name: this.currentProject },
				reload_doc: () => console.log('Mock reload_doc called'),
				refresh_field: () => console.log('Mock refresh_field called'),
				set_value: () => console.log('Mock set_value called')
			};

			// Render BOQ management table
			if (typeof render_boq_management_table === 'function') {
				render_boq_management_table(contentContainer, mockFrm, data.bills);
			} else {
				console.error('render_boq_management_table function not found');
				contentContainer.html('<div class="error-message">Failed to load BOQ table</div>');
			}

			// Hide loading, show content
			loadingContainer.stop(true, true).fadeOut(200, () => {
				contentContainer.stop(true, true).fadeIn(200);
			});

			// Setup content-specific event handlers
			this.setupContentEventHandlers();

			// Final size adjustment
			this.adjustModalSize();

		} catch (error) {
			console.error('Error rendering BOQ content:', error);
			this.modalElement.find('.fullscreen-content').html(`
				<div class="error-message">
					<i class="fa fa-exclamation-triangle"></i>
					Failed to render BOQ content. Please try refreshing.
				</div>
			`);
		}
	}

	/**
	 * Setup event listeners for full-screen modal
	 */
	setupEventListeners() {
		// Keyboard events
		$(document).on('keydown.boq-fullscreen', this.handleKeydown);

		// Window resize
		$(window).on('resize.boq-fullscreen', this.handleResize);

		// Modal click events
		this.modalElement.on('click', '.close-btn', () => this.closeFullScreen());
		this.modalElement.on('click', '.refresh-btn', () => this.refreshContent());

		// Prevent modal close on content click
		this.modalElement.on('click', '.fullscreen-content', (e) => e.stopPropagation());

		// Close on backdrop click
		this.modalElement.on('click', this.handleModalClick);
	}

	/**
	 * Setup content-specific event handlers
	 */
	setupContentEventHandlers() {
		// Enhanced bill expansion handling - Remove inline onclick to prevent double-toggling
		this.modalElement.find('.bill-header-row').removeAttr('onclick').off('click').on('click', (e) => {
			this.handleBillExpansion(e);
		});

		// Enhanced item expansion handling - Remove inline onclick to prevent double-toggling
		this.modalElement.find('.expand-btn').removeAttr('onclick').off('click').on('click', (e) => {
			this.handleItemExpansion(e);
		});

		// Fix z-index for any modals/dialogs opened within full-screen
		this.fixModalZIndex();
	}

	/**
	 * Handle bill expansion with enhanced stability
	 * @param {Event} e - Click event
	 */
	handleBillExpansion(e) {
		e.preventDefault();
		e.stopPropagation();

		const header = $(e.currentTarget);
		const section = header.closest('.bill-section');
		const billName = section.data('bill');
		const itemsContainer = section.find('.bill-items-container');
		const isExpanded = section.hasClass('expanded');

		// Store expansion state
		this.expansionStates.set(billName, !isExpanded);

		// Perform expansion/collapse with enhanced animation
		if (isExpanded) {
			itemsContainer.stop(true, false).slideUp(300, () => {
				section.removeClass('expanded');
			});
		} else {
			section.addClass('expanded');
			itemsContainer.stop(true, false).slideDown(300);
		}
	}

	/**
	 * Handle item expansion with single-click stability
	 * @param {Event} e - Click event
	 */
	handleItemExpansion(e) {
		e.preventDefault();
		e.stopPropagation();

		const button = $(e.currentTarget);
		const itemName = button.closest('tr').data('item');

		// Prevent multiple rapid clicks
		if (button.hasClass('processing')) {
			return;
		}

		button.addClass('processing');

		// Use existing transaction history toggle but with enhanced error handling
		try {
			if (typeof toggleTransactionHistory === 'function') {
				toggleTransactionHistory(itemName);
			}
		} catch (error) {
			console.error('Error toggling transaction history:', error);
			frappe.show_alert({
				message: __('Failed to load transaction history'),
				indicator: 'red'
			});
		} finally {
			// Remove processing state after a short delay
			setTimeout(() => {
				button.removeClass('processing');
			}, 500);
		}
	}

	/**
	 * Handle keyboard events
	 * @param {KeyboardEvent} e - Keyboard event
	 */
	handleKeydown(e) {
		if (!this.isFullScreenActive) return;

		switch (e.key) {
			case 'Escape':
				this.closeFullScreen();
				break;
			case 'F5':
				e.preventDefault();
				this.refreshContent();
				break;
		}
	}

	/**
	 * Handle window resize
	 */
	handleResize() {
		if (!this.isFullScreenActive) return;

		// Debounce resize handling
		clearTimeout(this.resizeTimeout);
		this.resizeTimeout = setTimeout(() => {
			this.adjustModalSize();
		}, 250);
	}

	/**
	 * Handle modal backdrop clicks
	 * @param {Event} e - Click event
	 */
	handleModalClick(e) {
		if (e.target === this.modalElement[0]) {
			this.closeFullScreen();
		}
	}

	/**
	 * Adjust modal size for current viewport
	 */
	adjustModalSize() {
		if (!this.modalElement) return;

		const content = this.modalElement.find('.fullscreen-content');
		const header = this.modalElement.find('.fullscreen-header');
		const headerHeight = header.outerHeight() || 60;

		content.css({
			'height': `calc(100vh - ${headerHeight}px)`,
			'max-height': `calc(100vh - ${headerHeight}px)`,
			'overflow-y': 'auto'
		});
	}

	/**
	 * Fix z-index for modals and dialogs
	 */
	fixModalZIndex() {
		// Ensure any new modals/dialogs have proper z-index
		$(document).on('show.bs.modal.boq-fullscreen', '.modal', (e) => {
			if (this.isFullScreenActive) {
				$(e.target).css('z-index', 10002);
				$(e.target).next('.modal-backdrop').css('z-index', 10001);
			}
		});

		// Fix existing modals
		$('.modal, .frappe-dialog').each((i, el) => {
			if ($(el).is(':visible') && this.isFullScreenActive) {
				$(el).css('z-index', 10002);
				$(el).next('.modal-backdrop').css('z-index', 10001);
			}
		});
	}

	/**
	 * Refresh full-screen content
	 */
	async refreshContent() {
		if (!this.currentProject) return;

		try {
			frappe.show_alert({ message: __('Refreshing BOQ data...'), indicator: 'blue' });

			// Show loading state
			const contentContainer = this.modalElement.find('#fullscreen-bills-container');
			const loadingContainer = this.modalElement.find('.loading-container');

			contentContainer.stop(true, true).fadeOut(200);
			loadingContainer.stop(true, true).fadeIn(200);

			// Fetch fresh data
			const data = await this.fetchBOQData(this.currentProject);

			// Re-render content
			this.renderBOQContent(data);

			frappe.show_alert({ message: __('BOQ data refreshed'), indicator: 'green' });

		} catch (error) {
			console.error('Error refreshing BOQ content:', error);
			// Restore UI state
			this.modalElement.find('.loading-container').hide();
			this.modalElement.find('#fullscreen-bills-container').fadeIn(200);

			frappe.show_alert({
				message: __('Failed to refresh BOQ data'),
				indicator: 'red'
			});
		}
	}

	/**
	 * Apply full-screen specific styles
	 */
	applyFullScreenStyles() {
		if ($('#boq-fullscreen-styles').length) return;

		const styles = `
			<style id="boq-fullscreen-styles">
				.boq-fullscreen-modal {
					position: fixed;
					top: 0;
					left: 0;
					width: 100vw;
					height: 100vh;
					background: rgba(0, 0, 0, 0.8);
					z-index: 10000;
					display: flex;
					flex-direction: column;
					overflow: hidden;
				}
				
				body.boq-modal-active {
					overflow: hidden !important;
				}
				
				.fullscreen-header {
					background: #fff;
					padding: 15px 20px;
					border-bottom: 1px solid #d1d8dd;
					display: flex;
					justify-content: space-between;
					align-items: center;
					flex-shrink: 0;
				}
				
				.fullscreen-title h2 {
					margin: 0;
					font-size: 18px;
					color: #1f272e;
				}
				
				.project-name {
					font-size: 14px;
					color: #6c7680;
					margin-left: 10px;
				}
				
				.fullscreen-actions {
					display: flex;
					gap: 10px;
				}
				
				.fullscreen-content {
					flex: 1;
					background: #fff;
					overflow-y: auto !important;
					position: relative;
				}
				
				.loading-container {
					display: flex;
					flex-direction: column;
					align-items: center;
					justify-content: center;
					height: 100%;
					color: #6c7680;
				}
				
				.loading-spinner {
					width: 40px;
					height: 40px;
					border: 3px solid #f3f3f3;
					border-top: 3px solid #2490ef;
					border-radius: 50%;
					animation: spin 1s linear infinite;
					margin-bottom: 15px;
				}
				
				@keyframes spin {
					0% { transform: rotate(0deg); }
					100% { transform: rotate(360deg); }
				}
				
				.loading-text {
					font-size: 14px;
				}
				
				.error-message {
					display: flex;
					flex-direction: column;
					align-items: center;
					justify-content: center;
					height: 100%;
					color: #ff5630;
					font-size: 16px;
				}
				
				.error-message i {
					font-size: 48px;
					margin-bottom: 15px;
				}
				
				/* Enhanced table styles for full-screen */
				.boq-fullscreen-modal .comprehensive-items-table {
					font-size: 12px;
				}
				
				.boq-fullscreen-modal .comprehensive-table-wrapper {
					overflow-x: auto;
					overflow-y: visible;
				}
				
				/* Prevent processing state visual feedback */
				.expand-btn.processing {
					opacity: 0.6;
					pointer-events: none;
				}
				
				/* Enhanced bill expansion animation */
				.boq-fullscreen-modal .bill-items-container {
					overflow: hidden;
				}
				
				/* Modal z-index fixes */
				.boq-fullscreen-modal .modal {
					z-index: 10002 !important;
				}
				
				.boq-fullscreen-modal .modal-backdrop {
					z-index: 10001 !important;
				}
				
				.boq-fullscreen-modal .frappe-dialog {
					z-index: 10002 !important;
				}
				
				/* Responsive adjustments */
				@media (max-width: 768px) {
					.fullscreen-header {
						padding: 10px 15px;
					}
					
					.fullscreen-title h2 {
						font-size: 16px;
					}
					
					.project-name {
						display: none;
					}
				}
			</style>
		`;

		$('head').append(styles);
	}

	/**
	 * Close full-screen modal and cleanup
	 */
	closeFullScreen() {
		if (!this.isFullScreenActive) return;

		// Remove event listeners
		$(document).off('.boq-fullscreen');
		$(window).off('.boq-fullscreen');

		// Exit browser full-screen if active
		if (document.fullscreenElement) {
			document.exitFullscreen().catch(console.error);
		}

		// Remove modal with animation
		if (this.modalElement) {
			this.modalElement.fadeOut(300, () => {
				this.modalElement.remove();
				this.modalElement = null;
			});
		}

		// Restore scroll position
		if (this.originalScrollPosition) {
			window.scrollTo(0, this.originalScrollPosition);
		}

		// Reset state
		this.isFullScreenActive = false;
		this.currentProject = null;
		this.expansionStates.clear();
		$('body').removeClass('boq-modal-active');

		// Remove styles
		$('#boq-fullscreen-styles').remove();
	}

	/**
	 * Check if full-screen is currently active
	 * @returns {boolean}
	 */
	isActive() {
		return this.isFullScreenActive;
	}

	/**
	 * Get current project
	 * @returns {string|null}
	 */
	getCurrentProject() {
		return this.currentProject;
	}
}

// Create global instance
window.boqFullScreenManager = new BOQFullScreenManager();

// Enhanced global functions for backward compatibility
window.openFullScreenBOQ = function (project) {
	window.boqFullScreenManager.initializeFullScreen(project);
};

window.closeFullScreenBOQ = function () {
	window.boqFullScreenManager.closeFullScreen();
};

window.refreshFullScreenBOQ = function () {
	window.boqFullScreenManager.refreshContent();
};

// Export for module usage
if (typeof module !== 'undefined' && module.exports) {
	module.exports = BOQFullScreenManager;
}