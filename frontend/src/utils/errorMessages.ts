/**
 * Maps exceptions to user-friendly error messages.
 * Logs raw errors to console in development mode only.
 * Prevents leakage of internal/server details to end users.
 */
export function mapErrorToUserMessage(error: unknown): string {
  // Log raw error to console in development (useful for debugging)
  if (process.env.NODE_ENV === 'development') {
    console.error('Error details:', error)
  }

  // Map to a safe, user-facing message
  if (error instanceof Error) {
    const msg = error.message.toLowerCase()
    
    // Network-related errors
    if (msg.includes('network') || msg.includes('fetch')) {
      return 'Network error. Please check your connection and try again.'
    }
    // Timeout errors
    if (msg.includes('timeout')) {
      return 'Request timed out. Please try again.'
    }
    // 4xx client errors
    if (msg.includes('400')) return 'Bad request. Please check your input and try again.'
    if (msg.includes('401')) return 'Authentication failed. Please log in and try again.'
    if (msg.includes('403')) return 'Access denied. You do not have permission to perform this action.'
    if (msg.includes('404')) return 'Resource not found. It may have been deleted or moved.'
    if (msg.includes('409')) return 'Conflict detected. This item may have been modified. Please refresh and try again.'
    if (msg.includes('422')) return 'Invalid input. Please check your entry and try again.'
    if (msg.includes('429')) return 'Too many requests. Please wait a moment and try again.'
    // 5xx server errors
    if (msg.includes('500')) return 'Server error. Please try again later.'
    if (msg.includes('502') || msg.includes('503')) return 'Service temporarily unavailable. Please try again later.'
  }

  // Generic fallback
  return 'An error occurred. Please try again.'
}
