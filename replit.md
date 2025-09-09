
# TTS Bot Project

## Overview

A comprehensive Telegram bot providing Text-to-Speech (TTS) services with advanced features including multiple voice options, credit-based system, referral rewards, link shortening for earning credits, payment processing, and robust admin management tools. Built with modern async Python using Pyrogram for Telegram integration and Edge TTS for high-quality voice synthesis.

## User Preferences

Preferred communication style: Simple, everyday Hindi-English mixed language for better user experience.

## Key Features

### 🎤 Text-to-Speech Services
- **Multiple Voice Options**: Various male and female voices in Hindi and English
- **High-Quality Audio**: Primary Edge TTS with gTTS fallback for reliability
- **Async Processing**: Non-blocking audio generation for better performance
- **Audio Quality Rating**: User feedback system for continuous improvement

### 💰 Credit System
- **Free Credits**: New users get welcome credits (configurable)
- **Earning System**: Credits through referrals and link interactions
- **Payment Integration**: UPI payment support with QR codes
- **Transaction History**: Complete audit trail of all credit movements
- **Dynamic Pricing**: Configurable per-word pricing for TTS requests

### 🔗 Referral & Link System
- **Referral Codes**: Unique codes for user referrals with bonus rewards
- **Link Shortening**: Multiple URL shortener API integrations
- **Credit Earning**: Automated credit distribution for link interactions
- **Referral Analytics**: Comprehensive tracking and statistics

### 🛡️ Admin Management
- **Owner Panel**: Complete administrative control interface
- **User Management**: Ban/unban, credit management, user analytics
- **System Settings**: Configurable bot parameters and pricing
- **Broadcast System**: Mass messaging capabilities for announcements
- **Database Backup**: Automated backup system with Telegram channel integration
- **Payment Verification**: Manual payment processing with approval system

### 📊 Analytics & Monitoring
- **Real-time Statistics**: User growth, usage patterns, system performance
- **Revenue Tracking**: Payment analytics and credit distribution monitoring
- **User Behavior**: TTS usage patterns and engagement metrics
- **System Health**: Database status, backup monitoring, error tracking

## System Architecture

### Backend Framework
- **Pyrogram 2.0+**: Modern async Telegram bot framework with full API support
- **SQLAlchemy 2.0+**: Advanced ORM with async support and connection pooling
- **Async Architecture**: Full asyncio implementation for concurrent request handling
- **Thread Pool Execution**: Optimized blocking operations handling

### Database Design
- **User Management**: Comprehensive user profiles with credits, activity tracking
- **TTS Request Logging**: Complete request history for analytics and billing
- **Credit Transaction System**: Detailed financial transaction tracking
- **Referral System**: Multi-level referral tracking with reward distribution
- **Payment Processing**: UPI payment requests with verification workflow
- **Link Management**: URL shortener integration with credit earning tracking
- **System Configuration**: Dynamic settings with real-time updates

### TTS Service Architecture
- **Primary Engine**: Microsoft Edge TTS for natural-sounding voices
- **Fallback System**: Google TTS (gTTS) for reliability and redundancy
- **Voice Library**: Extensive collection of Hindi and English voices
- **Quality Control**: Audio quality rating system for user feedback
- **Performance Optimization**: Async processing with proper resource management

### Security & Reliability
- **Input Validation**: Comprehensive sanitization of user inputs
- **Error Handling**: Graceful error recovery with user-friendly messages
- **Rate Limiting**: Built-in protection against abuse and spam
- **Database Resilience**: Connection pooling, retry logic, and backup systems
- **Session Management**: Secure Telegram session handling with persistence

### Payment & Monetization
- **UPI Integration**: QR code-based payment system with manual verification
- **Dynamic Pricing**: Configurable rates for credits and services
- **Payment Tracking**: Complete audit trail of all financial transactions
- **Automated Rewards**: Bonus credit distribution for various activities
- **Revenue Analytics**: Comprehensive financial reporting and insights

## External Dependencies

### Core Services
- **Telegram Bot API**: Primary interface through Pyrogram client
- **Microsoft Edge TTS**: High-quality text-to-speech synthesis
- **Google TTS**: Backup text-to-speech service for reliability

### Database Systems
- **SQLite**: Default database for development and simple deployments
- **PostgreSQL**: Production database with advanced features and scaling

### Third-party Integrations
- **URL Shortener APIs**: Universal handler supporting multiple shortener services
- **UPI Payment Systems**: QR code generation and payment verification
- **Telegram Channels**: Admin notifications, backups, and system monitoring

### Infrastructure Requirements
- **Python 3.8+**: Modern Python with async/await support
- **File System**: Temporary storage for audio generation and processing
- **Network Access**: HTTP/HTTPS for external API communications
- **Environment Configuration**: Secure configuration management with dotenv

## Configuration

### Environment Variables
- `API_ID`: Telegram API ID
- `API_HASH`: Telegram API Hash
- `BOT_TOKEN`: Telegram Bot Token
- `BOT_USERNAME`: Bot username for referral links
- `OWNER_ID`: Admin user ID for owner panel access
- `DATABASE_URL`: Database connection string
- `CHANNEL_ID`: Admin notification channel (optional)

### Deployment Requirements
- Python 3.8 or higher
- 512MB RAM minimum (1GB recommended)
- 1GB storage for logs and temporary files
- Stable internet connection for Telegram API
- Optional: PostgreSQL for production environments

## Development Status

This bot is actively maintained and continuously improved based on user feedback and technological advances. Regular updates include new TTS voices, enhanced admin features, improved payment processing, and performance optimizations.

## Support & Community

The bot includes comprehensive error handling, user-friendly messages in Hindi-English mix, and detailed logging for troubleshooting. Admin panel provides real-time monitoring and management capabilities for optimal user experience.
