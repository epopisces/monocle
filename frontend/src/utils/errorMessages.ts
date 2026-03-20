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
    if (msg.includes('400') || msg.includes('401') || msg.includes('403')) {
      return 'Request failed. Please try again.'
    }
    // 5xx server errors
    if (msg.includes('500') || msg.includes('502') || msg.includes('503')) {
      return 'Server error. Please try again later.'
    }
  }

  // Generic fallback
  return 'An error occurred. Please try again.'
}
