import { describe, it, expect, vi, afterEach } from 'vitest'
import { mapErrorToUserMessage } from './errorMessages'

describe('mapErrorToUserMessage', () => {
  afterEach(() => vi.clearAllMocks())

  it('returns generic network error message for NetworkError', () => {
    const error = new Error('NetworkError: failed to fetch')
    const message = mapErrorToUserMessage(error)
    expect(message).toBe('Network error. Please check your connection and try again.')
  })

  it('returns generic network error for fetch-related errors', () => {
    const error = new Error('Failed to fetch resource')
    const message = mapErrorToUserMessage(error)
    expect(message).toBe('Network error. Please check your connection and try again.')
  })

  it('returns timeout message for timeout errors', () => {
    const error = new Error('Request timeout after 30s')
    const message = mapErrorToUserMessage(error)
    expect(message).toBe('Request timed out. Please try again.')
  })

  it('returns timeout message for Timeout capitalized', () => {
    const error = new Error('TimeoutError')
    const message = mapErrorToUserMessage(error)
    expect(message).toBe('Request timed out. Please try again.')
  })

  it('returns client error message for 400', () => {
    const error = new Error('400 Bad Request')
    const message = mapErrorToUserMessage(error)
    expect(message).toBe('Request failed. Please try again.')
  })

  it('returns client error message for 401', () => {
    const error = new Error('401 Unauthorized')
    const message = mapErrorToUserMessage(error)
    expect(message).toBe('Request failed. Please try again.')
  })

  it('returns client error message for 403', () => {
    const error = new Error('403 Forbidden')
    const message = mapErrorToUserMessage(error)
    expect(message).toBe('Request failed. Please try again.')
  })

  it('returns server error message for 500', () => {
    const error = new Error('500 Internal Server Error')
    const message = mapErrorToUserMessage(error)
    expect(message).toBe('Server error. Please try again later.')
  })

  it('returns server error message for 502', () => {
    const error = new Error('502 Bad Gateway')
    const message = mapErrorToUserMessage(error)
    expect(message).toBe('Server error. Please try again later.')
  })

  it('returns server error message for 503', () => {
    const error = new Error('503 Service Unavailable')
    const message = mapErrorToUserMessage(error)
    expect(message).toBe('Server error. Please try again later.')
  })

  it('returns generic message for non-Error objects', () => {
    const message = mapErrorToUserMessage('some string error')
    expect(message).toBe('An error occurred. Please try again.')
  })

  it('returns generic message for null', () => {
    const message = mapErrorToUserMessage(null)
    expect(message).toBe('An error occurred. Please try again.')
  })

  it('returns generic message for undefined Error.message', () => {
    const error = new Error()
    error.message = ''
    const message = mapErrorToUserMessage(error)
    expect(message).toBe('An error occurred. Please try again.')
  })

  it('logs raw error to console in development mode', () => {
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {})
    const error = new Error('Original error details')
    
    // Mock NODE_ENV to 'development'
    const env = process.env.NODE_ENV
    process.env.NODE_ENV = 'development'
    
    mapErrorToUserMessage(error)
    expect(spy).toHaveBeenCalledWith('Error details:', error)
    
    process.env.NODE_ENV = env
    spy.mockRestore()
  })

  it('does not log to console in production mode', () => {
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {})
    const error = new Error('Original error details')
    
    // Mock NODE_ENV to 'production'
    const env = process.env.NODE_ENV
    process.env.NODE_ENV = 'production'
    
    mapErrorToUserMessage(error)
    expect(spy).not.toHaveBeenCalled()
    
    process.env.NODE_ENV = env
    spy.mockRestore()
  })
})
