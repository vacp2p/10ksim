/**
 * Configuration for API endpoint.
 * 
 * Uses build-time environment variable (baked into the bundle during docker build).
 * To change API URL, rebuild the image with:
 *   docker build --build-arg REACT_APP_API_URL=https://your-api.com -t frontend .
 */

export const API_BASE_URL = process.env.REACT_APP_API_URL || '';

export default {
    API_BASE_URL
};