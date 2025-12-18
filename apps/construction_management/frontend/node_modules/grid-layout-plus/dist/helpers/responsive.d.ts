import { Breakpoint, Breakpoints, Layout, ResponsiveLayout } from './types';
/**
 * Given a width, find the highest breakpoint that matches is valid for it (width > breakpoint).
 *
 * @param   breakpoints Breakpoints object (e.g. {lg: 1200, md: 960, ...})
 * @param   width Screen width.
 * @return        Highest breakpoint that is less than width.
 */
export declare function getBreakpointFromWidth(breakpoints: Breakpoints, width: number): Breakpoint;
/**
 * Given a breakpoint, get the # of cols set for it.
 * @param   breakpoint Breakpoint name.
 * @param   cols       Map of breakpoints to cols.
 * @return             Number of cols.
 */
export declare function getColsFromBreakpoint(breakpoint: Breakpoint, cols: Breakpoints): number;
/**
 * Given existing layouts and a new breakpoint, find or generate a new layout.
 *
 * This finds the layout above the new one and generates from it, if it exists.
 *
 * @param  orgLayout     Original layout.
 * @param  layouts     Existing layouts.
 * @param  breakpoints All breakpoints.
 * @param  breakpoint New breakpoint.
 * @param  breakpoint Last breakpoint (for fallback).
 * @param  cols       Column count at new breakpoint.
 * @param  verticalCompact Whether or not to compact the layout
 *   vertically.
 * @return              New layout.
 */
export declare function findOrGenerateResponsiveLayout(orgLayout: Layout, layouts: ResponsiveLayout, breakpoints: Breakpoints, breakpoint: Breakpoint, lastBreakpoint: Breakpoint, cols: number, verticalCompact: boolean): Layout;
export declare function generateResponsiveLayout(layout: Layout, breakpoints: Breakpoints, breakpoint: Breakpoint, lastBreakpoint: Breakpoint, cols: number, verticalCompact: boolean): Layout;
/**
 * Given breakpoints, return an array of breakpoints sorted by width. This is usually
 * e.g. ['xxs', 'xs', 'sm', ...]
 *
 * @param  breakpoints Key/value pair of breakpoint names to widths.
 * @return              Sorted breakpoints.
 */
export declare function sortBreakpoints(breakpoints: Breakpoints): Array<Breakpoint>;
