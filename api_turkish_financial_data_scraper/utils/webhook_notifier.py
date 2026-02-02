"""
Webhook notification system for scraping events
Supports Discord, Slack, and custom webhooks
"""
import logging
import aiohttp
import json
from typing import Dict, Any, Optional, List
from datetime import datetime
from config import config

logger = logging.getLogger(__name__)


class WebhookNotifier:
    """Send notifications via webhooks"""
    
    def __init__(self, webhook_url: Optional[str] = None):
        """
        Initialize webhook notifier
        
        Args:
            webhook_url: Webhook URL (can be from config or env)
        """
        self.webhook_url = webhook_url or getattr(config, 'webhook_url', None)
        if not self.webhook_url:
            # Try to get from environment
            import os
            self.webhook_url = os.getenv('WEBHOOK_URL') or os.getenv('DISCORD_WEBHOOK_URL')
    
    async def send_notification(
        self,
        title: str,
        message: str,
        color: Optional[int] = None,
        fields: Optional[List[Dict[str, Any]]] = None,
        footer: Optional[str] = None
    ) -> bool:
        """
        Send a notification via webhook
        
        Args:
            title: Notification title
            message: Main message content
            color: Color code (0xRRGGBB format, optional)
            fields: List of field dictionaries with 'name' and 'value'
            footer: Footer text
            
        Returns:
            Success status
        """
        if not self.webhook_url:
            logger.warning("No webhook URL configured, skipping notification")
            return False
        
        try:
            # Determine webhook type
            if 'discord.com' in self.webhook_url or 'discordapp.com' in self.webhook_url:
                payload = self._create_discord_payload(title, message, color, fields, footer)
            elif 'slack.com' in self.webhook_url:
                payload = self._create_slack_payload(title, message, fields)
            else:
                # Generic webhook
                payload = self._create_generic_payload(title, message, fields)
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.webhook_url,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    if response.status == 200 or response.status == 204:
                        logger.info(f"Webhook notification sent: {title}")
                        return True
                    else:
                        error_text = await response.text()
                        logger.error(f"Webhook failed: {response.status} - {error_text}")
                        return False
                        
        except Exception as e:
            logger.error(f"Error sending webhook notification: {e}", exc_info=True)
            return False
    
    def _create_discord_payload(
        self,
        title: str,
        message: str,
        color: Optional[int],
        fields: Optional[List[Dict[str, Any]]],
        footer: Optional[str]
    ) -> Dict[str, Any]:
        """Create Discord webhook payload"""
        embed = {
            "title": title,
            "description": message,
            "timestamp": datetime.utcnow().isoformat(),
        }
        
        if color is not None:
            embed["color"] = color
        elif "error" in title.lower() or "failed" in title.lower():
            embed["color"] = 0xFF0000  # Red
        elif "success" in title.lower() or "complete" in title.lower():
            embed["color"] = 0x00FF00  # Green
        else:
            embed["color"] = 0x0099FF  # Blue
        
        if fields:
            embed["fields"] = [
                {
                    "name": field.get("name", ""),
                    "value": str(field.get("value", "")),
                    "inline": field.get("inline", False)
                }
                for field in fields
            ]
        
        if footer:
            embed["footer"] = {"text": footer}
        
        return {"embeds": [embed]}
    
    def _create_slack_payload(
        self,
        title: str,
        message: str,
        fields: Optional[List[Dict[str, Any]]]
    ) -> Dict[str, Any]:
        """Create Slack webhook payload"""
        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": title
                }
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": message
                }
            }
        ]
        
        if fields:
            fields_block = {
                "type": "section",
                "fields": [
                    {
                        "type": "mrkdwn",
                        "text": f"*{field.get('name', '')}*\n{field.get('value', '')}"
                    }
                    for field in fields
                ]
            }
            blocks.append(fields_block)
        
        return {"blocks": blocks}
    
    def _create_generic_payload(
        self,
        title: str,
        message: str,
        fields: Optional[List[Dict[str, Any]]]
    ) -> Dict[str, Any]:
        """Create generic webhook payload"""
        payload = {
            "title": title,
            "message": message,
            "timestamp": datetime.utcnow().isoformat()
        }
        
        if fields:
            payload["data"] = {field.get("name"): field.get("value") for field in fields}
        
        return payload
    
    async def send_scraping_complete(
        self,
        scraper_type: str,
        stats: Dict[str, Any]
    ) -> bool:
        """
        Send scraping completion notification
        
        Args:
            scraper_type: Type of scraper (kap, bist, tradingview)
            stats: Statistics dictionary
            
        Returns:
            Success status
        """
        fields = [
            {"name": "Scraper", "value": scraper_type.upper(), "inline": True},
            {"name": "Status", "value": "✅ Complete", "inline": True}
        ]
        
        # Add stats to fields
        for key, value in stats.items():
            if key not in ["scraper", "status"]:
                fields.append({
                    "name": key.replace("_", " ").title(),
                    "value": str(value),
                    "inline": True
                })
        
        return await self.send_notification(
            title=f"✅ {scraper_type.upper()} Scraping Complete",
            message=f"Successfully scraped {scraper_type} data",
            fields=fields,
            footer="Turkish Financial Data Scraper"
        )
    
    async def send_scraping_error(
        self,
        scraper_type: str,
        error_message: str
    ) -> bool:
        """
        Send scraping error notification
        
        Args:
            scraper_type: Type of scraper
            error_message: Error message
            
        Returns:
            Success status
        """
        return await self.send_notification(
            title=f"❌ {scraper_type.upper()} Scraping Failed",
            message=f"Error: {error_message}",
            color=0xFF0000,
            footer="Turkish Financial Data Scraper"
        )
    
    async def send_sentiment_analysis_complete(
        self,
        report_count: int,
        positive: int,
        neutral: int,
        negative: int
    ) -> bool:
        """
        Send sentiment analysis completion notification
        
        Args:
            report_count: Total reports analyzed
            positive: Number of positive sentiments
            neutral: Number of neutral sentiments
            negative: Number of negative sentiments
            
        Returns:
            Success status
        """
        fields = [
            {"name": "Total Reports", "value": str(report_count), "inline": True},
            {"name": "Positive", "value": f"{positive} ({positive/report_count*100:.1f}%)", "inline": True},
            {"name": "Neutral", "value": f"{neutral} ({neutral/report_count*100:.1f}%)", "inline": True},
            {"name": "Negative", "value": f"{negative} ({negative/report_count*100:.1f}%)", "inline": True}
        ]
        
        return await self.send_notification(
            title="📊 Sentiment Analysis Complete",
            message=f"Analyzed {report_count} KAP reports",
            fields=fields,
            footer="Turkish Financial Data Scraper"
        )
