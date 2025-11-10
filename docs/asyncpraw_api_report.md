# asyncpraw API report (introspected)

- Generated at: 2025-11-10T20:38:43.883581Z
- Package: asyncpraw version: 7.8.1
- Modules scanned: 79

## Totals
- Public classes: 149
- Public class methods: 641
- Public class properties: 27
- Public module-level functions: 56

### Module: asyncpraw

### Module: asyncpraw.config

Class Config
  Properties:
  - short_url

### Module: asyncpraw.const

### Module: asyncpraw.endpoints

### Module: asyncpraw.exceptions

### Module: asyncpraw.models

### Module: asyncpraw.models.auth

Functions
- session

Class Auth
  Properties:
  - limits
  Methods:
  - authorize
  - implicit
  - parse
  - scopes
  - url

### Module: asyncpraw.models.base

Functions
- deepcopy

Class AsyncPRAWBase
  Methods:
  - parse

### Module: asyncpraw.models.comment_forest

Class CommentForest
  Methods:
  - list
  - replace_more

### Module: asyncpraw.models.front

Functions
- urljoin

Class Front
  Methods:
  - best
  - controversial
  - gilded
  - hot
  - new
  - parse
  - random_rising
  - rising
  - top

### Module: asyncpraw.models.helpers

Functions
- dumps

Class DraftHelper
  Methods:
  - create
  - parse

Class LiveHelper
  Methods:
  - create
  - info
  - now
  - parse

Class MultiredditHelper
  Methods:
  - create
  - parse

Class SubredditHelper
  Methods:
  - create
  - parse

### Module: asyncpraw.models.inbox

Functions
- stream_generator

Class Inbox
  Methods:
  - all
  - collapse
  - comment_replies
  - mark_all_read
  - mark_read
  - mark_unread
  - mentions
  - message
  - messages
  - parse
  - sent
  - stream
  - submission_replies
  - uncollapse
  - unread

### Module: asyncpraw.models.list

### Module: asyncpraw.models.list.base

Class BaseList
  Methods:
  - parse

### Module: asyncpraw.models.list.draft

Class DraftList
  Methods:
  - parse

### Module: asyncpraw.models.list.moderated

Class ModeratedList
  Methods:
  - parse

### Module: asyncpraw.models.list.redditor

Class RedditorList
  Methods:
  - parse

### Module: asyncpraw.models.list.trophy

Class TrophyList
  Methods:
  - parse

### Module: asyncpraw.models.listing

### Module: asyncpraw.models.listing.domain

Class DomainListing
  Methods:
  - controversial
  - hot
  - new
  - parse
  - random_rising
  - rising
  - top

### Module: asyncpraw.models.listing.generator

Functions
- deepcopy

Class ListingGenerator
  Methods:
  - parse

### Module: asyncpraw.models.listing.listing

Class FlairListing
  Properties:
  - after
  Methods:
  - parse

Class Listing
  Methods:
  - parse

Class ModNoteListing
  Properties:
  - after
  Methods:
  - parse

Class ModeratorListing
  Methods:
  - parse

Class ModmailConversationsListing
  Properties:
  - after
  Methods:
  - parse

### Module: asyncpraw.models.listing.mixins

### Module: asyncpraw.models.listing.mixins.base

Functions
- urljoin

Class BaseListingMixin
  Methods:
  - controversial
  - hot
  - new
  - parse
  - top

### Module: asyncpraw.models.listing.mixins.gilded

Functions
- urljoin

Class GildedListingMixin
  Methods:
  - gilded
  - parse

### Module: asyncpraw.models.listing.mixins.redditor

Functions
- urljoin

Class RedditorListingMixin
  Methods:
  - controversial
  - downvoted
  - gilded
  - gildings
  - hidden
  - hot
  - new
  - parse
  - saved
  - top
  - upvoted

Class SubListing
  Methods:
  - controversial
  - hot
  - new
  - parse
  - top

### Module: asyncpraw.models.listing.mixins.rising

Functions
- urljoin

Class RisingListingMixin
  Methods:
  - parse
  - random_rising
  - rising

### Module: asyncpraw.models.listing.mixins.submission

Class SubmissionListingMixin
  Methods:
  - duplicates
  - parse

### Module: asyncpraw.models.listing.mixins.subreddit

Functions
- urljoin

Class CommentHelper
  Methods:
  - parse

Class SubredditListingMixin
  Methods:
  - controversial
  - gilded
  - hot
  - new
  - parse
  - random_rising
  - rising
  - top

### Module: asyncpraw.models.mod_action

Class ModAction
  Properties:
  - mod
  Methods:
  - parse

### Module: asyncpraw.models.mod_note

Class ModNote
  Methods:
  - delete
  - parse

### Module: asyncpraw.models.mod_notes

Class BaseModNotes
  Methods:
  - create
  - delete

Class RedditModNotes
  Methods:
  - create
  - delete
  - things

Class RedditorModNotes
  Methods:
  - create
  - delete
  - subreddits

Class SubredditModNotes
  Methods:
  - create
  - delete
  - redditors

### Module: asyncpraw.models.preferences

Functions
- dumps

Class Preferences
  Methods:
  - update

### Module: asyncpraw.models.reddit

### Module: asyncpraw.models.reddit.base

Functions
- urlparse

Class RedditBase
  Methods:
  - load
  - parse

### Module: asyncpraw.models.reddit.collections

Functions
- deprecate_lazy

Class Collection
  Methods:
  - follow
  - load
  - parse
  - subreddit
  - unfollow

Class CollectionModeration
  Methods:
  - add_post
  - delete
  - parse
  - remove_post
  - reorder
  - update_description
  - update_display_layout
  - update_title

Class SubredditCollections
  Methods:
  - parse

Class SubredditCollectionsModeration
  Methods:
  - create
  - parse

### Module: asyncpraw.models.reddit.comment

Class Comment
  Properties:
  - fullname
  - is_root
  - replies
  - submission
  Methods:
  - award
  - block
  - clear_vote
  - collapse
  - delete
  - disable_inbox_replies
  - downvote
  - edit
  - enable_inbox_replies
  - gild
  - id_from_url
  - load
  - mark_read
  - mark_unread
  - parent
  - parse
  - refresh
  - reply
  - report
  - save
  - unblock_subreddit
  - uncollapse
  - unsave
  - upvote

Class CommentModeration
  Methods:
  - approve
  - author_notes
  - create_note
  - distinguish
  - ignore_reports
  - lock
  - remove
  - send_removal_message
  - show
  - undistinguish
  - unignore_reports
  - unlock

### Module: asyncpraw.models.reddit.draft

Class Draft
  Methods:
  - delete
  - load
  - parse
  - submit
  - update

### Module: asyncpraw.models.reddit.emoji

Functions
- deprecate_lazy

Class Emoji
  Methods:
  - delete
  - load
  - parse
  - update

Class SubredditEmoji
  Methods:
  - add
  - get_emoji

### Module: asyncpraw.models.reddit.inline_media

Class InlineGif

Class InlineImage

Class InlineMedia

Class InlineVideo

### Module: asyncpraw.models.reddit.live

Functions
- deprecate_lazy
- stream_generator

Class LiveContributorRelationship
  Methods:
  - accept_invite
  - invite
  - leave
  - remove
  - remove_invite
  - update
  - update_invite

Class LiveThread
  Methods:
  - discussions
  - get_update
  - load
  - parse
  - report
  - updates

Class LiveThreadContribution
  Methods:
  - add
  - close
  - update

Class LiveThreadStream
  Methods:
  - updates

Class LiveUpdate
  Properties:
  - fullname
  - thread
  Methods:
  - load
  - parse

Class LiveUpdateContribution
  Methods:
  - remove
  - strike

### Module: asyncpraw.models.reddit.message

Class Message
  Properties:
  - fullname
  - parent
  Methods:
  - block
  - collapse
  - delete
  - load
  - mark_read
  - mark_unread
  - parse
  - reply
  - unblock_subreddit
  - uncollapse

Class SubredditMessage
  Properties:
  - fullname
  - parent
  Methods:
  - block
  - collapse
  - delete
  - load
  - mark_read
  - mark_unread
  - mute
  - parse
  - reply
  - unblock_subreddit
  - uncollapse
  - unmute

### Module: asyncpraw.models.reddit.mixins

Functions
- dumps

Class ThingModerationMixin
  Methods:
  - approve
  - author_notes
  - create_note
  - distinguish
  - ignore_reports
  - lock
  - remove
  - send_removal_message
  - undistinguish
  - unignore_reports
  - unlock

Class UserContentMixin
  Methods:
  - award
  - clear_vote
  - delete
  - disable_inbox_replies
  - downvote
  - edit
  - enable_inbox_replies
  - gild
  - reply
  - report
  - save
  - unsave
  - upvote

### Module: asyncpraw.models.reddit.mixins.editable

Class EditableMixin
  Methods:
  - delete
  - edit

### Module: asyncpraw.models.reddit.mixins.fullname

Class FullnameMixin
  Properties:
  - fullname

### Module: asyncpraw.models.reddit.mixins.gildable

Class GildableMixin
  Methods:
  - award
  - gild

### Module: asyncpraw.models.reddit.mixins.inboxable

Class InboxableMixin
  Methods:
  - block
  - collapse
  - mark_read
  - mark_unread
  - unblock_subreddit
  - uncollapse

### Module: asyncpraw.models.reddit.mixins.inboxtoggleable

Class InboxToggleableMixin
  Methods:
  - disable_inbox_replies
  - enable_inbox_replies

### Module: asyncpraw.models.reddit.mixins.messageable

Class MessageableMixin
  Methods:
  - message

### Module: asyncpraw.models.reddit.mixins.modnote

Class ModNoteMixin
  Methods:
  - author_notes
  - create_note

### Module: asyncpraw.models.reddit.mixins.replyable

Class ReplyableMixin
  Methods:
  - reply

### Module: asyncpraw.models.reddit.mixins.reportable

Class ReportableMixin
  Methods:
  - report

### Module: asyncpraw.models.reddit.mixins.savable

Class SavableMixin
  Methods:
  - save
  - unsave

### Module: asyncpraw.models.reddit.mixins.votable

Class VotableMixin
  Methods:
  - clear_vote
  - downvote
  - upvote

### Module: asyncpraw.models.reddit.modmail

Functions
- snake_case_keys

Class ModmailAction
  Methods:
  - load
  - parse

Class ModmailConversation
  Methods:
  - archive
  - highlight
  - load
  - mute
  - parse
  - read
  - reply
  - unarchive
  - unhighlight
  - unmute
  - unread

Class ModmailMessage
  Methods:
  - load
  - parse

Class ModmailObject
  Methods:
  - load
  - parse

### Module: asyncpraw.models.reddit.more

Class MoreComments
  Methods:
  - comments
  - parse

### Module: asyncpraw.models.reddit.multi

Functions
- dumps

Class Multireddit
  Methods:
  - add
  - controversial
  - copy
  - delete
  - gilded
  - hot
  - load
  - new
  - parse
  - random_rising
  - remove
  - rising
  - sluggify
  - top
  - update

### Module: asyncpraw.models.reddit.poll

Class PollData
  Methods:
  - option
  - parse

Class PollOption
  Methods:
  - parse

### Module: asyncpraw.models.reddit.redditor

Functions
- dumps
- stream_generator

Class Redditor
  Properties:
  - fullname
  Methods:
  - block
  - controversial
  - distrust
  - downvoted
  - friend
  - friend_info
  - from_data
  - gild
  - gilded
  - gildings
  - hidden
  - hot
  - load
  - message
  - moderated
  - multireddits
  - new
  - parse
  - saved
  - top
  - trophies
  - trust
  - unblock
  - unfriend
  - upvoted

Class RedditorStream
  Methods:
  - comments
  - submissions

### Module: asyncpraw.models.reddit.removal_reasons

Functions
- deprecate_lazy

Class RemovalReason
  Methods:
  - delete
  - load
  - parse
  - update

Class SubredditRemovalReasons
  Methods:
  - add
  - get_reason

### Module: asyncpraw.models.reddit.rules

Functions
- quote

Class Rule
  Methods:
  - load
  - parse

Class RuleModeration
  Methods:
  - delete
  - update

Class SubredditRules
  Methods:
  - get_rule

Class SubredditRulesModeration
  Methods:
  - add
  - reorder

### Module: asyncpraw.models.reddit.submission

Functions
- dumps
- urljoin

Class Submission
  Properties:
  - fullname
  - shortlink
  Methods:
  - add_fetch_param
  - award
  - clear_vote
  - crosspost
  - delete
  - disable_inbox_replies
  - downvote
  - duplicates
  - edit
  - enable_inbox_replies
  - gild
  - hide
  - id_from_url
  - load
  - mark_visited
  - parse
  - reply
  - report
  - save
  - unhide
  - unsave
  - upvote

Class SubmissionFlair
  Methods:
  - choices
  - select

Class SubmissionModeration
  Methods:
  - approve
  - author_notes
  - contest_mode
  - create_note
  - distinguish
  - flair
  - ignore_reports
  - lock
  - nsfw
  - remove
  - send_removal_message
  - set_original_content
  - sfw
  - spoiler
  - sticky
  - suggested_sort
  - undistinguish
  - unignore_reports
  - unlock
  - unset_original_content
  - unspoiler
  - update_crowd_control_level

### Module: asyncpraw.models.reddit.subreddit

Functions
- XML
- deepcopy
- deprecate_lazy
- dumps
- permissions_string
- stream_generator
- urljoin

Class ContributorRelationship
  Methods:
  - add
  - leave
  - remove

Class ModeratorRelationship
  Methods:
  - add
  - invite
  - invited
  - leave
  - remove
  - remove_invite
  - update
  - update_invite

Class Modmail
  Methods:
  - bulk_read
  - conversations
  - create
  - subreddits
  - unread_count

Class Subreddit
  Properties:
  - fullname
  Methods:
  - controversial
  - gilded
  - hot
  - load
  - message
  - new
  - parse
  - post_requirements
  - random
  - random_rising
  - rising
  - search
  - sticky
  - submit
  - submit_gallery
  - submit_image
  - submit_poll
  - submit_video
  - subscribe
  - top
  - traffic
  - unsubscribe

Class SubredditFilters
  Methods:
  - add
  - remove

Class SubredditFlair
  Methods:
  - configure
  - delete
  - delete_all
  - set
  - update

Class SubredditFlairTemplates
  Methods:
  - delete
  - flair_type
  - update

Class SubredditLinkFlairTemplates
  Methods:
  - add
  - clear
  - delete
  - flair_type
  - reorder
  - update
  - user_selectable

Class SubredditModeration
  Methods:
  - accept_invite
  - edited
  - inbox
  - log
  - modqueue
  - reports
  - settings
  - spam
  - unmoderated
  - unread
  - update

Class SubredditModerationStream
  Methods:
  - edited
  - log
  - modmail_conversations
  - modqueue
  - reports
  - spam
  - unmoderated
  - unread

Class SubredditQuarantine
  Methods:
  - opt_in
  - opt_out

Class SubredditRedditorFlairTemplates
  Methods:
  - add
  - clear
  - delete
  - flair_type
  - reorder
  - update

Class SubredditRelationship
  Methods:
  - add
  - remove

Class SubredditStream
  Methods:
  - comments
  - submissions

Class SubredditStylesheet
  Methods:
  - delete_banner
  - delete_banner_additional_image
  - delete_banner_hover_image
  - delete_header
  - delete_image
  - delete_mobile_banner
  - delete_mobile_header
  - delete_mobile_icon
  - update
  - upload
  - upload_banner
  - upload_banner_additional_image
  - upload_banner_hover_image
  - upload_header
  - upload_mobile_banner
  - upload_mobile_header
  - upload_mobile_icon

Class SubredditWiki
  Methods:
  - create
  - get_page
  - revisions

### Module: asyncpraw.models.reddit.user_subreddit

Class UserSubreddit
  Properties:
  - fullname
  Methods:
  - controversial
  - gilded
  - hot
  - load
  - message
  - new
  - parse
  - post_requirements
  - random
  - random_rising
  - rising
  - search
  - sticky
  - submit
  - submit_gallery
  - submit_image
  - submit_poll
  - submit_video
  - subscribe
  - top
  - traffic
  - unsubscribe

Class UserSubredditModeration
  Methods:
  - accept_invite
  - edited
  - inbox
  - log
  - modqueue
  - reports
  - settings
  - spam
  - unmoderated
  - unread
  - update

### Module: asyncpraw.models.reddit.widgets

Functions
- dumps

Class Button
  Methods:
  - parse

Class ButtonWidget
  Methods:
  - parse

Class Calendar
  Methods:
  - parse

Class CalendarConfiguration
  Methods:
  - parse

Class CommunityList
  Methods:
  - parse

Class CustomWidget
  Methods:
  - parse

Class Hover
  Methods:
  - parse

Class IDCard
  Methods:
  - parse

Class Image
  Methods:
  - parse

Class ImageData
  Methods:
  - parse

Class ImageWidget
  Methods:
  - parse

Class Menu
  Methods:
  - parse

Class MenuLink
  Methods:
  - parse

Class ModeratorsWidget
  Methods:
  - parse

Class PostFlairWidget
  Methods:
  - parse

Class RulesWidget
  Methods:
  - parse

Class Styles
  Methods:
  - parse

Class Submenu
  Methods:
  - parse

Class SubredditWidgets
  Methods:
  - id_card
  - items
  - moderators_widget
  - parse
  - refresh
  - sidebar
  - topbar

Class SubredditWidgetsModeration
  Methods:
  - add_button_widget
  - add_calendar
  - add_community_list
  - add_custom_widget
  - add_image_widget
  - add_menu
  - add_post_flair_widget
  - add_text_area
  - reorder
  - upload_image

Class TextArea
  Methods:
  - parse

Class Widget
  Methods:
  - parse

Class WidgetEncoder
  Methods:
  - default
  - encode
  - iterencode

Class WidgetModeration
  Methods:
  - delete
  - update

### Module: asyncpraw.models.reddit.wikipage

Class WikiPage
  Methods:
  - discussions
  - edit
  - load
  - parse
  - revision
  - revisions

Class WikiPageModeration
  Methods:
  - add
  - remove
  - revert
  - settings
  - update

### Module: asyncpraw.models.redditors

Functions
- stream_generator

Class PartialRedditor

Class Redditors
  Methods:
  - new
  - parse
  - partial_redditors
  - popular
  - search
  - stream

### Module: asyncpraw.models.stylesheet

Class Stylesheet
  Methods:
  - parse

### Module: asyncpraw.models.subreddits

Functions
- stream_generator

Class Subreddits
  Methods:
  - default
  - gold
  - new
  - parse
  - popular
  - premium
  - recommended
  - search
  - search_by_name
  - search_by_topic
  - stream

### Module: asyncpraw.models.trophy

Class Trophy
  Methods:
  - parse

### Module: asyncpraw.models.user

Class User
  Methods:
  - blocked
  - contributor_subreddits
  - friends
  - karma
  - me
  - moderator_subreddits
  - multireddits
  - parse
  - pin
  - subreddits
  - trusted

### Module: asyncpraw.models.util

Functions
- deprecate_lazy
- permissions_string
- stream_generator
- wraps

Class BoundedSet
  Methods:
  - add

Class ExponentialCounter
  Methods:
  - counter
  - reset

### Module: asyncpraw.objector

Functions
- loads
- snake_case_keys

Class Objector
  Methods:
  - check_error
  - objectify
  - parse_error

### Module: asyncpraw.reddit

Functions
- copy
- deprecate_lazy
- getLogger
- session
- update_check
- urlparse

Class Reddit
  Properties:
  - read_only
  - validate_on_submit
  Methods:
  - close
  - comment
  - delete
  - domain
  - get
  - info
  - patch
  - post
  - put
  - random_subreddit
  - redditor
  - request
  - submission
  - username_available

### Module: asyncpraw.util

Functions
- camel_to_snake
- snake_case_keys

### Module: asyncpraw.util.cache

Class cachedproperty

### Module: asyncpraw.util.deprecate_args

Functions
- iscoroutinefunction
- wraps

### Module: asyncpraw.util.snake

Functions
- camel_to_snake
- snake_case_keys

### Module: asyncpraw.util.token_manager

Functions
- abstractmethod
- asynccontextmanager

Class BaseTokenManager
  Properties:
  - reddit
  Methods:
  - post_refresh_callback
  - pre_refresh_callback

Class FileTokenManager
  Properties:
  - reddit
  Methods:
  - post_refresh_callback
  - pre_refresh_callback

Class SQLiteTokenManager
  Properties:
  - reddit
  Methods:
  - close
  - connection
  - is_registered
  - post_refresh_callback
  - pre_refresh_callback
  - register
